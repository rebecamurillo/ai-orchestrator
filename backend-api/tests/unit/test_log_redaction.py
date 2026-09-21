"""Harness logs are redacted on every path out of `RealLogReader` (AD-5, hard rule 5).

**Why this exists.** `infrastructure/process/runner.py` hands a child's stdout and stderr
straight to the log file descriptor, so a harness CLI's own diagnostics are on disk before
any code can look at them. On 2026-09-20 OpenCode answered an unparseable config by printing
that config *with `{env:LITELLM_API_KEY}` already resolved* — putting a live Gateway key into
a log the API serves three ways. AD-10's "a name, never a value" holds for the file at rest
and for the `command` string; it cannot hold for text this system did not write.

`test_real_log_reader.py` covers what the reader reads and is untouched: a reader built with
no secrets behaves exactly as it did, which is what keeps those cases honest. This module
covers what it removes on the way out, and that both composition roots ask it to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.infrastructure.process.logs import RealLogReader, log_secrets
from orchestrator.infrastructure.redact import REDACTION
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT

SECRET = "sk-a-very-real-looking-gateway-key"
OTHER = "lf-sk-another-credential"

#: A page smaller than the fixture, so the limit branch of `read_from` is the one exercised.
PAGE = 2

#: The two composition roots that must pass the instance's secrets in.
ROOTS = (
    REPO_ROOT / "backend-api" / "src" / "orchestrator" / "api" / "providers.py",
    REPO_ROOT / "backend-api" / "src" / "orchestrator" / "infrastructure" / "dbos" / "startup.py",
)


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


def a_log(tmp_path: Path, *lines: str) -> str:
    log = tmp_path / "attempt.log"
    log.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
    return str(log)


def reader() -> RealLogReader:
    return RealLogReader((SECRET, OTHER))


# ── every read path ──────────────────────────────────────────────────────────


def test_the_tail_the_run_detail_shows_carries_no_secret(tmp_path: Path) -> None:
    """The 40-line tail on the Run detail is the one an Operator sees without asking."""
    path = a_log(tmp_path, "starting", f'"apiKey": "{SECRET}"', "done")

    assert reader().tail(path, 40) == ["starting", f'"apiKey": "{REDACTION}"', "done"]


def test_the_paged_endpoint_carries_no_secret(tmp_path: Path) -> None:
    path = a_log(tmp_path, f"before {SECRET} after")
    result = reader().read_from(path, 0, 200)

    assert result is not None
    assert result[0] == [f"before {REDACTION} after"]


def test_the_download_carries_no_secret(tmp_path: Path) -> None:
    """`?download=true` answers with the file; it must answer with the file minus this."""
    path = a_log(tmp_path, f"token={SECRET}")
    raw = reader().read_raw(path)

    assert raw is not None
    assert SECRET.encode() not in raw
    assert raw == f"token={REDACTION}\n".encode()


def test_more_than_one_secret_is_removed_from_one_line(tmp_path: Path) -> None:
    path = a_log(tmp_path, f"{SECRET} and {OTHER}")

    assert reader().tail(path, 40) == [f"{REDACTION} and {REDACTION}"]


def test_a_secret_split_across_two_lines_is_not_matched(tmp_path: Path) -> None:
    """Stated because it is a limit, not an oversight: this is a literal search, so a CLI
    that prints a credential transformed still leaks it. Stopping the leak and rotating the
    credential is the fix; this reduces the blast radius of the ones nobody predicted."""
    half = len(SECRET) // 2
    path = a_log(tmp_path, SECRET[:half], SECRET[half:])

    assert reader().tail(path, 40) == [SECRET[:half], SECRET[half:]]


# ── the paging cursor is a fact about the file, not about the redacted text ──


def test_the_cursor_still_counts_bytes_on_disk(tmp_path: Path) -> None:
    """`***` is shorter than what it replaces. A cursor derived from the redacted text would
    drift further from the file on every page until the poll read the wrong offsets."""
    path = a_log(tmp_path, f"one {SECRET}", "two")
    plain = RealLogReader().read_from(path, 0, 200)
    scrubbed = reader().read_from(path, 0, 200)

    assert plain is not None
    assert scrubbed is not None
    assert scrubbed[1] == plain[1] == Path(path).stat().st_size
    assert scrubbed[2] == plain[2] is True


def test_paging_with_a_limit_keeps_the_same_cursor_as_an_unredacted_read(
    tmp_path: Path,
) -> None:
    path = a_log(tmp_path, f"one {SECRET}", "two", "three")
    plain = RealLogReader().read_from(path, 0, PAGE)
    scrubbed = reader().read_from(path, 0, PAGE)

    assert plain is not None
    assert scrubbed is not None
    assert scrubbed[1] == plain[1]
    assert len(scrubbed[0]) == PAGE
    assert scrubbed[0] == [f"one {REDACTION}", "two"]


# ── an empty needle must never be load-bearing ───────────────────────────────


def test_a_blank_secret_redacts_nothing(tmp_path: Path) -> None:
    """`str.replace` with an empty needle inserts the marker between every character, which
    would make every log of a gateway-off instance unreadable."""
    path = a_log(tmp_path, "ordinary output")

    assert RealLogReader(("", SECRET)).tail(path, 40) == ["ordinary output"]


def test_a_reader_with_no_secrets_returns_the_file_unchanged(tmp_path: Path) -> None:
    path = a_log(tmp_path, f"token={SECRET}")

    assert RealLogReader().tail(path, 40) == [f"token={SECRET}"]


# ── what the instance hands the reader ───────────────────────────────────────


def test_every_credential_the_instance_holds_is_redacted(settings: Settings) -> None:
    """Derived from the `SecretStr` fields themselves, so a credential added to `Settings`
    tomorrow is covered without anyone remembering to come back here."""
    secrets = log_secrets(settings)

    for secret in (
        settings.litellm_api_key,
        settings.litellm_spend_key,
        settings.langfuse_secret_key,
        settings.github_token,
        settings.orchestrator_token,
    ):
        assert secret.get_secret_value() in secrets


def test_blank_credentials_are_dropped_rather_than_passed_on(settings: Settings) -> None:
    assert "" not in log_secrets(settings)


@pytest.mark.parametrize("root", ROOTS, ids=lambda p: p.name)
def test_the_composition_root_passes_the_instances_secrets_in(root: Path) -> None:
    """`RealLogReader()` is safe in a test and wrong in production, so the default is held in
    place by this rather than by memory."""
    body = root.read_text()

    assert "RealLogReader(log_secrets(settings))" in body
    assert "RealLogReader()" not in body
