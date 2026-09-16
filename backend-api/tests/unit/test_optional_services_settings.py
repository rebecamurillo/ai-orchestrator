"""Optional-services settings: gateway and tracing switches (story 9-1).

Acceptance criteria:
- .env.example environment → gateway_enabled=True, tracing_enabled=True
- Blank LITELLM_BASE_URL → gateway_enabled=False, tracing_enabled=True
- Blank LANGFUSE_BASE_URL → tracing_enabled=False, gateway_enabled=True
- Both blank → both properties False
- Whitespace-only LITELLM_BASE_URL → gateway_enabled=False
- Deleted LITELLM_BASE_URL → ValidationError naming litellm_base_url
- Deleted LANGFUSE_BASE_URL → ValidationError naming langfuse_base_url
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
from orchestrator.infrastructure.settings import Settings

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


# ── deleted URLs raise ValidationError ───────────────────────────────────────


def test_deleted_litellm_base_url_raises_naming_field(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "litellm_base_url" in str(excinfo.value).lower()


def test_deleted_langfuse_base_url_raises_naming_field(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("LANGFUSE_BASE_URL")
    with pytest.raises(ValidationError) as excinfo:
        Settings()
    assert "langfuse_base_url" in str(excinfo.value).lower()


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
