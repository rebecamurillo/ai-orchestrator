"""The `codex` environment builder and `scripts/harness/codex.sh`, held to one list (AD-10, AD-5).

`tests/unit/test_harness_env_contract.py` does this for `claude` and says in its own docstring
that Epic 7 reuses its shape for the other two harnesses; it is frozen, so this is a sibling
module rather than two more cases in it. The parsing helpers are imported from it rather than
re-typed, because two copies of "what the bash array says" is the drift the whole idea exists to
catch.

Codex is the harness with *no* aliases: `codex.sh` declares `HARNESS_ENV_ALIASES=()` because
Codex reads the contract names directly — `env_key = "LITELLM_API_KEY"` and `env_http_headers`
mapping the five AD-11 headers to `ORCH_*` names, both written into `config.toml` as *names*.
So the assertion this module owes is the empty one, and it has to be stated rather than skipped:
an alias silently added to the script would otherwise never be missed in Python.

The one name the builder does add is `CODEX_HOME`. It is not an alias — the script `export`s it
itself — but a harness process receives exactly what `env_for` returns plus the runner's own five
names, and `CODEX_HOME` is in neither list, so without it Codex would read `~/.codex` instead of
the configured `AGENT_HOME/.codex`. The brief's `env_for` line names it beside `HOME`, `PATH`,
`LANG` and `TERM` for that reason.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import env_for
from orchestrator.infrastructure.harness.codex.adapter import CODEX_HOME, codex_aliases
from orchestrator.infrastructure.harness.env import BASE_NAMES, HARNESS_ENV_CONTRACT
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT
from tests.unit.test_harness_env_contract import CONTRACT_SCRIPT, bash_array

CODEX_SCRIPT = REPO_ROOT / "scripts" / "harness" / "codex.sh"

#: The Project's own variables, as `env_for` receives them decrypted (AD-5).
PROJECT_ENV = {"MY_FLAG": "on", "NPM_CONFIG_REGISTRY": "https://registry.example"}


@pytest.fixture
def settings(env: dict[str, str]) -> Settings:
    return Settings()


def an_attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="running",
        harness="codex",
        model="gpt-5-codex",
    )


def a_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=Decimal("40"),
        created_at=datetime(2026, 9, 9, tzinfo=UTC),
    )


def built(settings: Settings, *, log_content: bool = False) -> dict[str, str]:
    attempt = an_attempt()
    return env_for(
        attempt,
        run=a_run(attempt),
        project_slug="acme",
        project_env=PROJECT_ENV,
        log_content=log_content,
        settings=settings,
        story_id="7-1",
        aliases=codex_aliases(settings.agent_home),
    )


# ── the script declares no aliases, and that is asserted rather than skipped ──


def test_the_codex_script_declares_an_empty_alias_array() -> None:
    """Codex reads the contract names directly (`env_key`, `env_http_headers`)."""
    body = CODEX_SCRIPT.read_text()
    match = re.search(r"^HARNESS_ENV_ALIASES=\((.*?)\)", body, re.MULTILINE | re.DOTALL)

    assert match, "codex.sh: no HARNESS_ENV_ALIASES=( … ) declaration"
    assert match.group(1).split() == []


def test_the_script_names_the_contract_variable_the_gateway_key_travels_in() -> None:
    """`env_key = "LITELLM_API_KEY"` is why there is no alias to declare."""
    assert 'env_key = "LITELLM_API_KEY"' in CODEX_SCRIPT.read_text()
    assert "LITELLM_API_KEY" in HARNESS_ENV_CONTRACT


def test_the_script_exports_the_home_the_builder_supplies() -> None:
    """Two statements of one name, tied together: the script's `export` and `CODEX_HOME`."""
    assert re.search(rf"^export {CODEX_HOME}=", CODEX_SCRIPT.read_text(), re.MULTILINE)


# ── env_for produces exactly the contract, the project, the base and CODEX_HOME ──


def test_the_key_set_is_the_contract_the_project_the_base_names_and_codex_home(
    settings: Settings,
) -> None:
    expected = (
        set(bash_array(CONTRACT_SCRIPT, "HARNESS_ENV_CONTRACT"))
        | set(PROJECT_ENV)
        | set(BASE_NAMES)
        | {CODEX_HOME}
    )

    assert set(built(settings)) == expected


def test_codex_home_points_at_the_configured_agent_home(settings: Settings) -> None:
    """`codex.sh configure` writes `config.toml` under exactly this directory."""
    assert built(settings)[CODEX_HOME] == str(Path(settings.agent_home) / ".codex")


def test_the_content_switch_adds_no_environment_name_for_this_harness(
    settings: Settings,
) -> None:
    """Unlike Claude's `OTEL_LOG_*` pair, Codex takes the switch on the command line."""
    assert set(built(settings, log_content=True)) == set(built(settings))
    assert built(settings, log_content=True)["ORCH_LOG_CONTENT"] == "1"


# ── AD-5: no secret beyond the gateway key and the Langfuse keys ─────────────


def test_no_credential_beyond_the_gateway_and_langfuse_keys_reaches_the_process(
    settings: Settings,
) -> None:
    values = set(built(settings).values())

    assert settings.litellm_api_key.get_secret_value() in values
    assert settings.langfuse_secret_key.get_secret_value() in values
    assert settings.github_token.get_secret_value() not in values
    assert settings.litellm_spend_key.get_secret_value() not in values


def test_a_project_may_not_smuggle_a_forbidden_name_into_a_codex_process(
    settings: Settings,
) -> None:
    attempt = an_attempt()

    result = env_for(
        attempt,
        run=a_run(attempt),
        project_slug="acme",
        project_env={"GITHUB_TOKEN": "leak", "CODEX_HOME": "/tmp/mine", "MY_FLAG": "on"},
        log_content=False,
        settings=settings,
        story_id="7-1",
        aliases=codex_aliases(settings.agent_home),
    )

    assert "GITHUB_TOKEN" not in result
    assert result[CODEX_HOME] == str(Path(settings.agent_home) / ".codex")
    assert result["MY_FLAG"] == "on"
