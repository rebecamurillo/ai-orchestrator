"""Settings is the only reader of the environment (AD-20)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from orchestrator.infrastructure.settings import Settings

# Every variable of the spine's variable table that belongs to backend-api.
BACKEND_VARIABLES = {
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SECRET_KEY",
    "DATABASE_URL",
    "DBOS_APPLICATION_VERSION",
    "GITHUB_TOKEN",
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LOCAL_MODELS",
    "MAX_ACTIVE_RUNS",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
    "LANGFUSE_ENVIRONMENT",
    "BMAD_VERSION",
    "CLAUDE_CODE_VERSION",
    "CODEX_VERSION",
    "OPENCODE_VERSION",
    "LANGFUSE_OPENCODE_PLUGIN_VERSION",
    "CLAUDE_ALLOWED_TOOLS",
    "WORK_DIR",
    "AGENT_HOME",
    "LOG_PROMPT_CONTENT_DEFAULT",
    "LOG_LEVEL",
    "BACKEND_API_PORT",
}

# `DATABASE_URL` belongs here because the committed contract embeds POSTGRES_PASSWORD in it.
CREDENTIAL_VARIABLES = {
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SECRET_KEY",
    "DATABASE_URL",
    "GITHUB_TOKEN",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_SECRET_KEY",
}

EXPECTED_BACKEND_API_PORT = 8000
EXPECTED_MAX_ACTIVE_RUNS = 2
EXPECTED_DBOS_APPLICATION_VERSION = 1


def test_every_backend_variable_is_a_typed_field(env: dict[str, str]) -> None:
    fields = {name.upper() for name in Settings.model_fields}
    assert fields == BACKEND_VARIABLES


def test_settings_parses_the_env_example_contract(env: dict[str, str]) -> None:
    settings = Settings()

    assert settings.orchestrator_token.get_secret_value() == env["ORCHESTRATOR_TOKEN"]
    assert settings.backend_api_port == EXPECTED_BACKEND_API_PORT
    assert settings.max_active_runs == EXPECTED_MAX_ACTIVE_RUNS
    assert settings.dbos_application_version == EXPECTED_DBOS_APPLICATION_VERSION
    assert settings.log_prompt_content_default is False
    assert settings.log_level == "info"
    assert settings.local_models == ["local-coder", "local-general"]
    assert "Task" in settings.claude_allowed_tools
    assert settings.work_dir.as_posix() == "/work"
    assert settings.agent_home.as_posix() == "/home/agent"


# ── secrets (hard rule 5) ────────────────────────────────────────────────────


@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARIABLES))
def test_every_credential_bearing_variable_is_secret_str(
    env: dict[str, str], variable: str
) -> None:
    settings = Settings()
    assert isinstance(getattr(settings, variable.lower()), SecretStr)


@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARIABLES))
def test_no_credential_value_from_the_contract_appears_in_repr(
    env: dict[str, str], variable: str
) -> None:
    """Value-scoped, not name-scoped: a new leaking field fails without editing a list."""
    assert env[variable] not in repr(Settings())


def test_the_database_password_is_not_reachable_through_any_field(env: dict[str, str]) -> None:
    """POSTGRES_PASSWORD is embedded in DATABASE_URL; a plain-`str` URL would expose it."""
    assert f":{env['POSTGRES_PASSWORD']}@" not in repr(Settings())


def test_no_unredacted_field_carries_url_userinfo(env: dict[str, str]) -> None:
    """Generic guard: any future field holding `scheme://user:pass@host` must be SecretStr."""
    settings = Settings()

    for name in Settings.model_fields:
        value = getattr(settings, name)
        if isinstance(value, SecretStr):
            continue
        rendered = str(value)
        assert "://" not in rendered or "@" not in rendered, name


def test_secret_fields_render_as_a_mask(env: dict[str, str]) -> None:
    assert "**********" in repr(Settings())


# ── validation ───────────────────────────────────────────────────────────────


def test_missing_required_variable_is_named(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ORCHESTRATOR_TOKEN")

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert "orchestrator_token" in str(excinfo.value).lower()


@pytest.mark.parametrize("level", ["bogus", "verbose", "INF", ""])
def test_an_unknown_log_level_is_rejected_at_the_boundary(env: dict[str, str], level: str) -> None:
    with pytest.raises(ValidationError, match="log_level"):
        Settings(log_level=level)


@pytest.mark.parametrize("level", ["debug", "info", "warning", "error", "critical"])
def test_the_log_levels_the_stack_uses_are_accepted(env: dict[str, str], level: str) -> None:
    assert Settings(log_level=level).log_level == level


@pytest.mark.parametrize("value", [0, -1])
def test_zero_or_negative_concurrency_is_rejected(env: dict[str, str], value: int) -> None:
    """AD-12 treats queue concurrency as live; 0 would park every Run forever."""
    with pytest.raises(ValidationError, match="max_active_runs"):
        Settings(max_active_runs=value)


@pytest.mark.parametrize("port", [0, -1, 65536])
def test_a_port_outside_the_tcp_range_is_rejected(env: dict[str, str], port: int) -> None:
    with pytest.raises(ValidationError, match="backend_api_port"):
        Settings(backend_api_port=port)


def test_a_non_positive_engine_version_is_rejected(env: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="dbos_application_version"):
        Settings(dbos_application_version=0)


@pytest.mark.parametrize("field", ["work_dir", "agent_home"])
def test_a_relative_volume_path_is_rejected(env: dict[str, str], field: str) -> None:
    """`WORK_DIR=` would otherwise land clones in the process working directory."""
    with pytest.raises(ValidationError, match=field):
        Settings(**{field: Path("relative/path")})


@pytest.mark.parametrize("field", ["local_models", "claude_allowed_tools"])
def test_an_empty_comma_separated_value_is_rejected(env: dict[str, str], field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        Settings(**{field: "  "})


def test_a_comma_separated_value_is_split_and_stripped(env: dict[str, str]) -> None:
    assert Settings(local_models=" a , b ").local_models == ["a", "b"]
