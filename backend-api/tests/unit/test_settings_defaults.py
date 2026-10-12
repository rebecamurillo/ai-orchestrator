"""Boot on the MUST-HAVE secrets alone; every other setting has a code default.

Operator decision 2026-09-20, two-tier configuration contract; reaffirmed 2026-09-30:
"make the system bootable with strictly minimal environment variables — environment
variables can be undefined/null; all others should not block system boot." Before it,
every field was required, so each setting a story added was a breaking change for every
existing `.env`, and a stale file crash-looped the stack.

Three things are asserted here, and the first is the one that keeps "one source of truth"
true after the change:

- **No drift.** For every defaulted field, the code default equals the value the committed
  `.env.example` declares. Compared by *parsing both sides through `Settings`* rather than
  by comparing strings, so the comparison is over typed values and a re-spelling of a cron
  or a path cannot pass it. The gateway/tracing group is excluded by name: its code default
  is "off" while its contract line deliberately shows the "on" example.
- **The minimal boot works.** `Settings()` constructs with exactly the four MUST-HAVE
  variables set and every other contract name genuinely unset — not blank.
- **The MUST-HAVE tier still refuses.** Each of the four, removed on its own, raises
  `ValidationError` naming the field.

And, because the Operator's words are "undefined/null": a variable left *blank* behaves
like an absent one for every defaulted field, so a stale `.env` that still carries
`MAX_ACTIVE_RUNS=` boots instead of failing on `int("")`.
"""

from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from orchestrator.infrastructure.settings import BLANK_IS_MEANINGFUL, Settings
from tests.unit.conftest import ENV_EXAMPLE, parse_env_example

#: The tier that refuses to start (Operator decision 2026-09-20; reaffirmed 2026-09-30).
MUST_HAVE = ("ORCHESTRATOR_TOKEN", "ORCHESTRATOR_SECRET_KEY", "DATABASE_URL", "GITHUB_TOKEN")

#: Fields whose code default is deliberately *not* the contract value: the contract shows a
#: working "on" example (a host URL, a placeholder key), while the shipped default is "off",
#: because an integration nobody configured must not look configured — and a placeholder
#: credential in the source would be a literal secret-shaped string (hard rule 5).
OFF_BY_DEFAULT = frozenset(
    {
        "litellm_base_url",
        "litellm_api_key",
        "litellm_spend_key",
        "langfuse_base_url",
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_project_id",
        # Notifications (story O-8, 2026-10-12): blank is the off switch, so the contract
        # line is blank too and the code default equals it; listed because the sourceable
        # and blank-is-meaningful checks below enumerate the group.
        "notify_webhook_url",
        "notify_webhook_secret",
        "public_base_url",
    }
)

#: Defaulted fields whose type makes an empty string ambiguous — `int("")`, `Decimal("")`
#: and an empty comma-separated list all refuse, and `Path("")` is the process working
#: directory. These are the ones a stale `.env` would crash-loop the stack on.
AMBIGUOUS_WHEN_BLANK = (
    ("MAX_ACTIVE_RUNS", "max_active_runs"),
    ("DBOS_APPLICATION_VERSION", "dbos_application_version"),
    ("HUMAN_WAIT_SECONDS", "human_wait_seconds"),
    ("WORKTREE_RETENTION_DAYS", "worktree_retention_days"),
    ("BACKEND_API_PORT", "backend_api_port"),
    ("READINESS_BUDGET_USD", "readiness_budget_usd"),
    ("READINESS_MODELS", "readiness_models"),
    ("LOCAL_MODELS", "local_models"),
    ("CLAUDE_ALLOWED_TOOLS", "claude_allowed_tools"),
    ("WORK_DIR", "work_dir"),
    ("AGENT_HOME", "agent_home"),
    ("TEMPLATES_DIR", "templates_dir"),
    ("HARNESS_SCRIPTS_DIR", "harness_scripts_dir"),
    ("KIT_DIR", "kit_dir"),
    ("LOG_LEVEL", "log_level"),
    ("LOG_PROMPT_CONTENT_DEFAULT", "log_prompt_content_default"),
    ("CLAUDE_SUBSCRIPTION_AUTH", "claude_subscription_auth"),
    ("ORCH_TEST_MODE", "orch_test_mode"),
    ("LITELLM_SPEND_MATCH", "litellm_spend_match"),
    ("CLONE_CHECK_CRON", "clone_check_cron"),
    ("BMAD_VERSION", "bmad_version"),
)


def _clear_every_contract_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unset every name either side of the contract knows, however the host spells it.

    `Settings` is case-insensitive, so a lower-cased host variable (`log_level`) would
    shadow the absence this module is about — clear by upper-cased name, the way the
    shared `env` fixture does.
    """
    known = set(parse_env_example(ENV_EXAMPLE)) | {n.upper() for n in Settings.model_fields}
    for name in list(os.environ):
        if name.upper() in known:
            monkeypatch.delenv(name, raising=False)


@pytest.fixture
def minimal_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Exactly the MUST-HAVE variables, and nothing else — the minimal boot."""
    contract = parse_env_example(ENV_EXAMPLE)
    _clear_every_contract_name(monkeypatch)
    for name in MUST_HAVE:
        monkeypatch.setenv(name, contract[name])
    return contract


# ── the minimal boot ─────────────────────────────────────────────────────────


def test_settings_constructs_from_the_must_have_variables_alone(
    minimal_env: dict[str, str],
) -> None:
    """The acceptance test of the whole change: four variables, and the app binds."""
    settings = Settings()

    assert settings.orchestrator_token.get_secret_value() == minimal_env["ORCHESTRATOR_TOKEN"]
    assert settings.github_token.get_secret_value() == minimal_env["GITHUB_TOKEN"]


def test_no_other_contract_name_is_set_while_the_minimal_boot_is_proved(
    minimal_env: dict[str, str],
) -> None:
    """A guard on the fixture: an inherited host variable would make the test above vacuous.

    Genuinely unset, not blank — blank is a different case, proved separately below.
    """
    leaked = {
        name
        for name in minimal_env
        if name not in MUST_HAVE and name.upper() in {key.upper() for key in os.environ}
    }

    assert leaked == set(), sorted(leaked)


def test_an_integration_nobody_configured_is_off(minimal_env: dict[str, str]) -> None:
    """Blank base URLs are the off switch, and that is what the minimal boot gets."""
    settings = Settings()

    assert settings.gateway_enabled is False
    assert settings.tracing_enabled is False


def test_the_container_paths_are_what_the_image_ships(minimal_env: dict[str, str]) -> None:
    """The reason no Dockerfile changes: the defaults *are* the image's own layout."""
    settings = Settings()

    assert settings.work_dir == Path("/work")
    assert settings.agent_home == Path("/home/agent")
    assert settings.templates_dir == Path("/app/templates")
    assert settings.harness_scripts_dir == Path("/app/scripts/harness")
    assert settings.kit_dir == Path("/app/deploy/kit")


# ── the MUST-HAVE tier still refuses ─────────────────────────────────────────


@pytest.mark.parametrize("variable", MUST_HAVE)
def test_a_missing_must_have_variable_refuses_and_names_the_field(
    minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.delenv(variable)

    with pytest.raises(ValidationError) as excinfo:
        Settings()

    assert variable.lower() in str(excinfo.value).lower()


def test_exactly_these_four_fields_are_required(minimal_env: dict[str, str]) -> None:
    """Bounded by enumeration: a fifth required field would make the contract two-tier in
    name only, and is the regression this change exists to prevent."""
    required = {
        name.upper() for name, field in Settings.model_fields.items() if field.is_required()
    }

    assert required == set(MUST_HAVE)


# ── the drift guard: code default == the committed contract value ────────────


DEFAULTED_FIELDS = sorted(
    name for name, field in Settings.model_fields.items() if not field.is_required()
)


def test_there_are_defaulted_fields_to_check() -> None:
    """A guard on the parametrisation below: an empty list would make it vacuous."""
    assert len(DEFAULTED_FIELDS) > len(OFF_BY_DEFAULT)


@pytest.mark.parametrize("field_name", [n for n in DEFAULTED_FIELDS if n not in OFF_BY_DEFAULT])
def test_the_code_default_is_the_value_the_contract_declares(
    field_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One source of truth, kept true by comparison rather than by discipline.

    Both sides are parsed through `Settings`, so the comparison is over typed values:
    `READINESS_BUDGET_USD=5` and `Decimal("5")` are the same fact, and a re-spelled cron
    or a differently-ordered model list is not.
    """
    contract = parse_env_example(ENV_EXAMPLE)
    _clear_every_contract_name(monkeypatch)
    for name, value in contract.items():
        monkeypatch.setenv(name, value)
    from_contract = Settings()

    _clear_every_contract_name(monkeypatch)
    for name in MUST_HAVE:
        monkeypatch.setenv(name, contract[name])
    from_defaults = Settings()

    assert getattr(from_defaults, field_name) == getattr(from_contract, field_name)


@pytest.mark.parametrize("field_name", sorted(OFF_BY_DEFAULT))
def test_the_off_by_default_group_ships_blank_rather_than_the_contracts_example(
    field_name: str, minimal_env: dict[str, str]
) -> None:
    """The named exception, asserted rather than merely excluded: these default to blank,
    which is what makes an unconfigured instance honest about being unconfigured. A
    placeholder credential as a code default would also be a secret-shaped literal in the
    source (hard rule 5)."""
    value = getattr(Settings(), field_name)
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value

    assert raw == ""


def test_every_off_by_default_name_is_a_defaulted_field() -> None:
    """The exception list cannot quietly name something that is not defaulted at all."""
    assert OFF_BY_DEFAULT <= set(DEFAULTED_FIELDS)


def test_the_readiness_defaults_cover_every_harness(minimal_env: dict[str, str]) -> None:
    """`_covers_every_harness` is unchanged, so the default has to satisfy it."""
    settings = Settings()

    assert set(settings.readiness_models) == {"claude", "codex", "local"}
    assert settings.readiness_budget_usd == Decimal("5")


# ── undefined *or* null: a blank value falls back to the default ─────────────


@pytest.mark.parametrize(("variable", "field_name"), AMBIGUOUS_WHEN_BLANK, ids=lambda x: x)
def test_a_blank_value_falls_back_to_the_default_rather_than_refusing(
    variable: str, field_name: str, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`MAX_ACTIVE_RUNS=` in a stale `.env` is the same intent as leaving the line out.

    Without this, `int("")` refuses at start-up and the stack crash-loops — the failure
    mode the Operator described on 2026-09-30 ("we need to specify empty variables,
    otherwise boot fails").
    """
    default = getattr(Settings(), field_name)
    monkeypatch.setenv(variable, "")

    assert getattr(Settings(), field_name) == default


@pytest.mark.parametrize(("variable", "field_name"), AMBIGUOUS_WHEN_BLANK, ids=lambda x: x)
def test_a_whitespace_only_value_falls_back_too(
    variable: str, field_name: str, minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A line edited down to `FOO= ` is the same absence with a stray space."""
    default = getattr(Settings(), field_name)
    monkeypatch.setenv(variable, "   ")

    assert getattr(Settings(), field_name) == default


@pytest.mark.parametrize("field_name", sorted(BLANK_IS_MEANINGFUL))
def test_blank_still_means_blank_for_the_gateway_and_tracing_group(
    field_name: str, env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback above must not eat the documented off switch: for these seven, blank is
    a value the application reads, not an absence."""
    monkeypatch.setenv("LITELLM_BASE_URL", "")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "")
    monkeypatch.setenv(field_name.upper(), "")

    value = getattr(Settings(), field_name)
    raw = value.get_secret_value() if isinstance(value, SecretStr) else value

    assert raw == ""


def test_the_blank_is_meaningful_set_is_exactly_the_off_by_default_group() -> None:
    """Two lists, one fact: a field whose blank is meaningful is a field whose default is
    blank. Enumerated so adding a member is a visible edit rather than a silent widening."""
    assert BLANK_IS_MEANINGFUL == OFF_BY_DEFAULT


def test_a_blank_must_have_variable_is_not_rewritten_by_the_fallback(
    minimal_env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fallback applies to defaulted fields only — a required field has nothing to fall
    back to, so its behaviour is exactly what it was before this change."""
    monkeypatch.setenv("ORCHESTRATOR_TOKEN", "")

    assert Settings().orchestrator_token.get_secret_value() == ""
