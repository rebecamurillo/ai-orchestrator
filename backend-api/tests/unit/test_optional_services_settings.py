"""Optional-services settings: gateway and tracing switches (story 9-1).

Acceptance criteria:
- .env.example environment → gateway_enabled=True, tracing_enabled=True
- Blank LITELLM_BASE_URL → gateway_enabled=False, tracing_enabled=True
- Blank LANGFUSE_BASE_URL → tracing_enabled=False, gateway_enabled=True
- Both blank → both properties False
- Whitespace-only LITELLM_BASE_URL → gateway_enabled=False
- Deleted LITELLM_BASE_URL → gateway off, and the app still starts
- Deleted LANGFUSE_BASE_URL → tracing off, and the app still starts
- Non-blank LITELLM_BASE_URL + blank LITELLM_API_KEY → ValidationError naming both, with
  disable hint ("blank")
- Non-blank LANGFUSE_BASE_URL + blank LANGFUSE_PUBLIC_KEY → ValidationError naming both
- Non-blank LANGFUSE_BASE_URL + blank LANGFUSE_SECRET_KEY → ValidationError naming both
- Non-blank LANGFUSE_BASE_URL + blank LANGFUSE_PROJECT_ID → ValidationError naming both
- Both off (all keys blank) → two "gateway disabled"/"tracing disabled" warning lines from
  main(), no credential field in any log record
"""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from orchestrator import main as composition_root
from orchestrator.infrastructure.harness import build_harnesses
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

# ── both enabled (default) ────────────────────────────────────────────────────


def test_env_example_has_gateway_and_tracing_enabled(env: dict[str, str]) -> None:
    settings = Settings()
    assert settings.gateway_enabled is True
    assert settings.tracing_enabled is True


# ── gateway_enabled property ──────────────────────────────────────────────────


def test_blank_litellm_base_url_disables_gateway(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    settings = Settings()
    assert settings.gateway_enabled is False
    assert settings.tracing_enabled is True


def test_whitespace_only_litellm_base_url_disables_gateway(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "   ")
    settings = Settings()
    assert settings.gateway_enabled is False


# ── tracing_enabled property ──────────────────────────────────────────────────


def test_blank_langfuse_base_url_disables_tracing(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    settings = Settings()
    assert settings.tracing_enabled is False
    assert settings.gateway_enabled is True


def test_both_base_urls_blank_disables_both(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    settings = Settings()
    assert settings.gateway_enabled is False
    assert settings.tracing_enabled is False


# ── a deleted URL is the service off, not a refusal ──────────────────────────
#
# Revised under Operator decision 2026-09-20, two-tier configuration contract; reaffirmed
# 2026-09-30 ("environment variables can be undefined/null ... all others should not block
# system boot"). These two cases used to assert that an *absent* base URL refused start-up
# naming the field; under the two-tier contract an absent optional variable is its code
# default, and the code default for both base URLs is blank — the documented off switch.
# The replacement asserts strictly more than the old pair did: the absence is tolerated,
# the right service is the one that went off, the other stays on, and — for the gateway —
# the `local` harness disappears from the registry, which is the behaviour an operator
# actually observes. Blank and whitespace-only still mean off (above), and a half-configured
# service still refuses (below): neither was weakened.


def test_deleted_litellm_base_url_disables_the_gateway_and_still_starts(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL")

    settings = Settings()

    assert settings.litellm_base_url == ""
    assert settings.gateway_enabled is False
    assert settings.tracing_enabled is True
    assert "local" not in build_harnesses(settings, FakeProcessRunner())


def test_deleted_langfuse_base_url_disables_tracing_and_still_starts(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LANGFUSE_BASE_URL")

    settings = Settings()

    assert settings.langfuse_base_url == ""
    assert settings.tracing_enabled is False
    assert settings.gateway_enabled is True


def test_a_deleted_gateway_url_is_the_same_as_a_blank_one(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The point of the revision, stated once: absent and blank are one behaviour now."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    blank = Settings()
    monkeypatch.delenv("LITELLM_BASE_URL")
    absent = Settings()

    assert absent.litellm_base_url == blank.litellm_base_url
    assert absent.gateway_enabled == blank.gateway_enabled


# ── half-config raises ValidationError naming both fields ─────────────────────


def test_non_blank_gateway_url_blank_api_key_raises_naming_both_with_disable_hint(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LITELLM_API_KEY", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    error = str(excinfo.value).lower()
    assert "litellm_base_url" in error
    assert "litellm_api_key" in error
    assert "blank" in error


def test_non_blank_tracing_url_blank_public_key_raises_naming_both(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    error = str(excinfo.value).lower()
    assert "langfuse_base_url" in error
    assert "langfuse_public_key" in error


def test_non_blank_tracing_url_blank_secret_key_raises_naming_both(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    error = str(excinfo.value).lower()
    assert "langfuse_base_url" in error
    assert "langfuse_secret_key" in error


def test_non_blank_tracing_url_blank_project_id_raises_naming_both(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    error = str(excinfo.value).lower()
    assert "langfuse_base_url" in error
    assert "langfuse_project_id" in error


# ── warning lines from main() ─────────────────────────────────────────────────

#: Credential field names that must never appear as keys in any log record.
_CREDENTIAL_FIELDS = frozenset(
    {
        "litellm_api_key",
        "litellm_spend_key",
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_project_id",
    }
)


def test_gateway_only_off_emits_only_gateway_disabled_warning(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Blank LITELLM_BASE_URL → exactly one 'gateway disabled' record, no 'tracing disabled'."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")

    monkeypatch.setattr(composition_root.uvicorn, "run", lambda *_a, **_kw: None)
    composition_root.main()

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    gateway_records = [r for r in records if r.get("event") == "gateway disabled"]
    tracing_records = [r for r in records if r.get("event") == "tracing disabled"]

    assert len(gateway_records) == 1, gateway_records
    assert len(tracing_records) == 0, tracing_records
    assert gateway_records[0].get("spend") == "provisional"


def test_tracing_only_off_emits_only_tracing_disabled_warning(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Blank LANGFUSE_BASE_URL → exactly one 'tracing disabled' record, no 'gateway disabled'."""
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")

    monkeypatch.setattr(composition_root.uvicorn, "run", lambda *_a, **_kw: None)
    composition_root.main()

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    gateway_records = [r for r in records if r.get("event") == "gateway disabled"]
    tracing_records = [r for r in records if r.get("event") == "tracing disabled"]

    assert len(gateway_records) == 0, gateway_records
    assert len(tracing_records) == 1, tracing_records
    assert tracing_records[0].get("traces") == "absent"


def test_both_off_emits_warning_lines_for_each_disabled_service_no_credential_in_log(
    env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """main() emits one structured warning per disabled service; no credential field leaks."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LITELLM_API_KEY", "")
    monkeypatch.setenv("LITELLM_SPEND_KEY", "")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("LANGFUSE_PROJECT_ID", "")

    monkeypatch.setattr(composition_root.uvicorn, "run", lambda *_a, **_kw: None)
    composition_root.main()

    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    records = [json.loads(line) for line in lines]

    gateway_records = [r for r in records if r.get("event") == "gateway disabled"]
    tracing_records = [r for r in records if r.get("event") == "tracing disabled"]

    assert len(gateway_records) == 1, gateway_records
    assert len(tracing_records) == 1, tracing_records

    assert gateway_records[0].get("spend") == "provisional"
    assert tracing_records[0].get("traces") == "absent"

    for record in records:
        leaked = _CREDENTIAL_FIELDS & record.keys()
        assert not leaked, f"credential field(s) {leaked!r} leaked into log record: {record}"
