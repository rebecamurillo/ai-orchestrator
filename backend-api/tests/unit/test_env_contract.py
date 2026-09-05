"""`.env.example` is the configuration contract; `make lint` fails when it drifts (AD-20)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from check_env_contract import (
    COMPOSE_ONLY_VARIABLES,
    ContractError,
    compare,
    env_example_variables,
    parse_env_example,
    settings_variables,
)

from tests.unit.conftest import ENV_EXAMPLE, REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "check_env_contract.py"

#: The success line's exact shape (`main()`'s `sys.stdout.write` format), captured so a
#: test can check the reported numbers rather than merely that some text is present.
SUCCESS_LINE = re.compile(
    r"^env contract: (\d+) settings fields and (\d+) \S+ variables agree \((\d+) allowlisted\)$"
)


def _run_script(*args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the check the way `make lint` does — as a command, in this interpreter."""
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "backend-api" / "src")}
    return subprocess.run(  # fixed argv, no shell
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        check=False,
    )


# ── the committed state ──────────────────────────────────────────────────────


def test_the_committed_contract_matches_settings() -> None:
    missing, extra, absent = compare(settings_variables(), env_example_variables())

    assert missing == []
    assert extra == []
    assert absent == []


def test_the_check_passes_as_a_command() -> None:
    result = _run_script()

    assert result.returncode == 0, result.stdout + result.stderr
    assert "ModuleNotFoundError" not in result.stderr


def test_the_success_line_reports_both_sides() -> None:
    result = _run_script()

    assert f"{len(settings_variables())} settings fields" in result.stdout
    assert f"{len(env_example_variables())} {ENV_EXAMPLE.name} variables" in result.stdout


def test_the_success_line_counts_are_exact_and_derived_not_hardcoded() -> None:
    """A substring check tolerates drift a literal wouldn't catch either: `"25" in "125
    settings..."` is still true. This pins the full line's three numbers exactly against
    fresh calls to `settings_variables()`, `env_example_variables()` and
    `COMPOSE_ONLY_VARIABLES`, so a later story that adds one more setting changes this
    test's expectation along with the implementation instead of breaking it."""
    result = _run_script()

    match = SUCCESS_LINE.match(result.stdout.strip())
    assert match is not None, result.stdout
    fields_count, contract_count, allowlisted_count = (int(group) for group in match.groups())

    assert fields_count == len(settings_variables())
    assert contract_count == len(env_example_variables())
    assert allowlisted_count == len(COMPOSE_ONLY_VARIABLES)


def test_the_reported_field_count_shrinks_when_the_contract_does(tmp_path: Path) -> None:
    """Proof the count comes from reading the file, not from some cached figure: parsing a
    trimmed copy of the committed contract directly (bypassing the script's own strict
    agreement check, which a merely-trimmed file would otherwise fail) must report one
    fewer contract variable than the committed file does."""
    trimmed = tmp_path / ".env.example"
    kept = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines(keepends=True)
        if not line.startswith("LOG_LEVEL=")
    ]
    trimmed.write_text("".join(kept))

    assert len(env_example_variables(trimmed)) == len(env_example_variables()) - 1


# ── drift, in both directions ────────────────────────────────────────────────


def test_a_settings_field_absent_from_the_contract_is_named() -> None:
    missing, extra, _absent = compare({"LOG_LEVEL", "NEW_SETTING"}, {"LOG_LEVEL"})

    assert missing == ["NEW_SETTING"]
    assert extra == []


def test_a_contract_variable_with_no_settings_field_is_named() -> None:
    missing, extra, _absent = compare({"LOG_LEVEL"}, {"LOG_LEVEL", "STRAY_VARIABLE"})

    assert missing == []
    assert extra == ["STRAY_VARIABLE"]


def test_compose_and_web_client_variables_are_allowlisted() -> None:
    missing, extra, _absent = compare(set(), set(COMPOSE_ONLY_VARIABLES))

    assert missing == []
    assert extra == []


def test_deleting_an_allowlisted_variable_is_caught() -> None:
    """Compose and the web-client need these; the allowlist must not hide their removal."""
    contract = set(COMPOSE_ONLY_VARIABLES) - {"POSTGRES_DB"}

    _missing, _extra, absent = compare(set(), contract)

    assert absent == ["POSTGRES_DB"]


def test_the_allowlist_covers_exactly_the_non_backend_contract_variables() -> None:
    assert COMPOSE_ONLY_VARIABLES == {
        "ORCHESTRATOR_SESSION_SECRET",
        "BACKEND_API_URL",
        "WEB_CLIENT_PORT",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    }
    assert COMPOSE_ONLY_VARIABLES <= env_example_variables()


def test_no_allowlisted_variable_is_also_a_settings_field() -> None:
    """The allowlist exists for variables no backend module reads — prove it stays that way."""
    assert not (COMPOSE_ONLY_VARIABLES & settings_variables())


def test_the_script_reports_a_missing_variable_and_exits_non_zero(tmp_path: Path) -> None:
    trimmed = tmp_path / ".env.example"
    kept = [
        line
        for line in ENV_EXAMPLE.read_text().splitlines(keepends=True)
        if not line.startswith("LOG_LEVEL=")
    ]
    trimmed.write_text("".join(kept))

    result = _run_script("--env-example", str(trimmed))

    assert result.returncode != 0
    assert "LOG_LEVEL" in result.stdout + result.stderr


# ── parsing the contract file ────────────────────────────────────────────────


def test_a_value_may_contain_a_hash(tmp_path: Path) -> None:
    """A password like `p#ss` must not be truncated at the comment character."""
    path = tmp_path / ".env.example"
    path.write_text("# a comment\nA_VALUE=p#ss   # trailing comment\nB_VALUE=plain\n")

    assert parse_env_example(path) == {"A_VALUE": "p#ss", "B_VALUE": "plain"}


def test_a_duplicate_declaration_is_an_error(tmp_path: Path) -> None:
    """Two lines for one name pass silently in compose; the later one wins."""
    path = tmp_path / ".env.example"
    path.write_text("LOG_LEVEL=info\nLOG_LEVEL=debug\n")

    with pytest.raises(ContractError, match="declared twice"):
        parse_env_example(path)


def test_a_mis_cased_name_is_an_error(tmp_path: Path) -> None:
    """Settings is case-insensitive, so `Log_level=` would be read but never checked."""
    path = tmp_path / ".env.example"
    path.write_text("Log_level=info\n")

    with pytest.raises(ContractError, match="uppercase"):
        parse_env_example(path)


def test_an_export_prefix_is_understood(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text("export LOG_LEVEL=info\n")

    assert parse_env_example(path) == {"LOG_LEVEL": "info"}


def test_a_quoted_value_is_unwrapped(tmp_path: Path) -> None:
    path = tmp_path / ".env.example"
    path.write_text("A=\"quoted value\"\nB='single'\n")

    assert parse_env_example(path) == {"A": "quoted value", "B": "single"}


def test_a_missing_contract_file_is_named_not_a_traceback(tmp_path: Path) -> None:
    result = _run_script("--env-example", str(tmp_path / "absent.env"))

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "absent.env" in result.stdout + result.stderr
