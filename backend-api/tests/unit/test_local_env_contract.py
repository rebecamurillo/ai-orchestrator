"""The `local` environment builder and `scripts/harness/opencode.sh`, held to one list (AD-10).

`tests/unit/test_harness_env_contract.py` does this for `claude` and says in its own docstring
that Epic 7 reuses its shape for the other two harnesses; it is frozen, so this is a sibling
module — the third — rather than more cases in it. The parsing helpers are imported from it
rather than re-typed, because two copies of "what the bash array says" is the drift the whole
idea exists to catch.

`local` is the harness with *two* aliases, and they are the reason this test matters more here
than for `codex`: `LANGFUSE_BASEURL` is the Langfuse plugin's own spelling of a contract name
this system spells `LANGFUSE_BASE_URL`, and `LANGFUSE_USER_ID` is how a generation the plugin
sends is attributed to the Run at all (AD-11). A name added to the script and not to the
builder would leave the plugin silently un-keyed — one whole harness's traces landing under no
Run — which is exactly the failure a green readiness gate must not be able to hide.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import env_for
from orchestrator.infrastructure.harness.env import BASE_NAMES
from orchestrator.infrastructure.harness.opencode.adapter import local_aliases
from orchestrator.infrastructure.harness.opencode.sessions import STORE_RELATIVE_PATH
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT
from tests.unit.test_harness_env_contract import CONTRACT_SCRIPT, alias_names, bash_array

OPENCODE_SCRIPT = REPO_ROOT / "scripts" / "harness" / "opencode.sh"

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
        harness="local",
        model="local-coder",
    )


def a_run(attempt: Attempt) -> Run:
    return Run(
        id=attempt.run_id,
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("40"),
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
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
        story_id="7-3",
        traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
        aliases=local_aliases,
    )


# ── the script's two aliases are the builder's two names ─────────────────────


def test_the_script_declares_exactly_the_three_aliases_the_builder_adds() -> None:
    """Third alias added by the fix of 2026-09-20 — see `local_aliases`' own docstring."""
    assert set(alias_names(OPENCODE_SCRIPT)) == {
        "LANGFUSE_BASEURL",
        "LANGFUSE_USER_ID",
        "OPENCODE_LANGFUSE_TAGS",
    }


def test_each_alias_is_derived_from_the_contract_name_the_script_names_it_from() -> None:
    """The right-hand side of `NAME=source` is a contract name, and the builder must derive
    that alias from that source — not from a value of its own and not from another contract
    name's.

    "Derived" rather than "copied" since 2026-09-20: two of the three copy their source
    verbatim, and `OPENCODE_LANGFUSE_TAGS` renders it, because OpenCode substitutes
    `{env:NAME}` into `opencode.json` before parsing the file and the raw JSON array's quotes
    broke the string it landed in. `test_local_adapter.py` holds the rendering itself; what
    this asserts is that the script and the builder name the same source.
    """
    sources = dict(
        word.split("=", 1) for word in bash_array(OPENCODE_SCRIPT, "HARNESS_ENV_ALIASES")
    )

    assert sources == {
        "LANGFUSE_BASEURL": "LANGFUSE_BASE_URL",
        "LANGFUSE_USER_ID": "ORCH_RUN_ID",
        "OPENCODE_LANGFUSE_TAGS": "ORCH_LANGFUSE_TAGS",
    }
    assert set(sources.values()) <= set(bash_array(CONTRACT_SCRIPT, "HARNESS_ENV_CONTRACT"))


# ── env_for produces exactly the two script lists, plus project and base ─────


def test_the_key_set_is_the_two_script_lists_plus_the_project_and_the_base_names(
    settings: Settings,
) -> None:
    expected = (
        set(bash_array(CONTRACT_SCRIPT, "HARNESS_ENV_CONTRACT"))
        | set(alias_names(OPENCODE_SCRIPT))
        | set(PROJECT_ENV)
        | set(BASE_NAMES)
    )

    assert set(built(settings)) == expected


def test_the_plugin_is_keyed_by_the_run_the_attempt_belongs_to(settings: Settings) -> None:
    """The brief's own acceptance criterion, over the real builder: `LANGFUSE_USER_ID` is
    `run_id`, which is the only thing `attempt_observed` for `local` can find a generation by."""
    environment = built(settings)

    assert environment["LANGFUSE_USER_ID"] == environment["ORCH_RUN_ID"]


def test_the_plugins_base_url_is_the_contracts(settings: Settings) -> None:
    environment = built(settings)

    assert environment["LANGFUSE_BASEURL"] == environment["LANGFUSE_BASE_URL"]


def test_the_content_switch_adds_no_environment_name_for_this_harness(
    settings: Settings,
) -> None:
    """`[verify; else record "no content switch"]`: the plugin documents none, so the switch
    travels as the contract name it already is and nothing is derived from it."""
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


def test_a_project_may_not_smuggle_a_forbidden_name_into_a_local_process(
    settings: Settings,
) -> None:
    attempt = an_attempt()

    result = env_for(
        attempt,
        run=a_run(attempt),
        project_slug="acme",
        project_env={"GITHUB_TOKEN": "leak", "LANGFUSE_USER_ID": "someone-else", "MY_FLAG": "on"},
        log_content=False,
        settings=settings,
        story_id="7-3",
        aliases=local_aliases,
    )

    assert "GITHUB_TOKEN" not in result
    assert result["LANGFUSE_USER_ID"] == result["ORCH_RUN_ID"]
    assert result["MY_FLAG"] == "on"


def test_the_script_writes_its_config_from_environment_names_and_never_values() -> None:
    """AD-10: `opencode.sh configure` references `{env:NAME}`, so no adapter and no config
    file holds a credential — the one reason this harness needs no secret alias at all."""
    body = OPENCODE_SCRIPT.read_text()

    assert '"apiKey": "{env:LITELLM_API_KEY}"' in body
    assert "{env:ORCH_RUN_ID}" in body


def test_the_tags_header_reads_the_escaped_alias_and_not_the_raw_contract_name() -> None:
    """The defect of 2026-09-20, in the one line that carried it. `{env:ORCH_LANGFUSE_TAGS}`
    put a JSON array's quotes inside a JSON string, so OpenCode could not parse its own config
    and exited 1 before reading the prompt — on every dispatch, for as long as the Gateway was
    enabled. `test_opencode_config_substitution.py` proves the replacement parses."""
    body = OPENCODE_SCRIPT.read_text()

    assert '"langfuse_tags": "{env:OPENCODE_LANGFUSE_TAGS}"' in body
    assert "{env:ORCH_LANGFUSE_TAGS}" not in body


def test_readiness_makes_opencode_parse_the_config_it_just_wrote() -> None:
    """Before this, `probe` and `doctor` ran `--version` and curled the Gateway — neither
    reads `opencode.json` — so a config every dispatch died on left readiness green."""
    body = OPENCODE_SCRIPT.read_text()

    assert "config_parses()" in body
    assert "opencode models" in body
    assert "config unparseable" in body


def test_the_store_path_the_script_documents_is_the_one_the_adapter_reads() -> None:
    """Two statements of one path, tied together: the script's own invocation comment and
    `sessions.py`'s constant. Both are `[verify]` until 7.4, and they must move together."""
    assert f"~/{STORE_RELATIVE_PATH}" in OPENCODE_SCRIPT.read_text()


def test_the_pinned_version_the_script_defaults_to_is_the_settings_one(
    settings: Settings,
) -> None:
    """AD-16: the image installs `OPENCODE_VERSION` and the `harness` row pins the same value."""
    assert f': "${{OPENCODE_VERSION:={settings.opencode_version}}}"' in OPENCODE_SCRIPT.read_text()


def test_the_models_the_script_configures_are_the_settings_aliases(settings: Settings) -> None:
    """`configure` writes one model entry per `LOCAL_MODELS` alias, and the adapter defaults
    to the first of them — two readers of one list, so it is asserted rather than assumed."""
    assert settings.local_models
    assert ': "${LOCAL_MODELS:=' in OPENCODE_SCRIPT.read_text()
