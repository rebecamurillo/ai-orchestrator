"""Claude Code against the Gateway on a Max/Pro subscription (AD-5, AD-10, AD-11).

Two ways to reach LiteLLM, and they differ in what the `Authorization` header carries.

*API-key mode*, the default and everything before this module: `ANTHROPIC_AUTH_TOKEN` holds
the Gateway's virtual key, Claude Code sends it as `Authorization: Bearer …`, LiteLLM
validates it and calls Anthropic with the provider key the host holds. `claude_aliases`
builds that, and nothing here changes it.

*Subscription mode*: the operator has logged Claude Code in against their own Claude
subscription, so `Authorization` carries that OAuth token and LiteLLM forwards it upstream
(`forward_client_headers_to_llm_api: true`, host-side). The header is occupied, so the
virtual key has to travel somewhere else — `x-litellm-api-key`, which is the header LiteLLM
reads a key from when `Authorization` is not its own. `ANTHROPIC_AUTH_TOKEN` must therefore
be *absent*: set, it overrides the stored credentials and the subscription is never used.

So the mode is exactly two edits to one alias set — one name dropped, one header added —
and this suite pins both, plus the far more important thing: that the default is untouched.
`ALIASES` stays `{"claude": claude_aliases}` (`test_harness_registry.py` pins that equality)
and `test_harness_env_contract.py` keeps comparing `claude_aliases` against the bash arrays;
subscription mode is a second table `build_harness_env` selects with a setting, not an edit
to the first.

**The contract deviation is deliberate and is stated here so it is not discovered.**
`scripts/harness/claude.sh` declares `HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=… …)`, and
in subscription mode the environment does not carry that name. The script's array describes
the default; the equality `test_harness_env_contract.py` asserts is about the default, and
`test_the_key_set_is_the_default_one_minus_the_token` below is the statement of what the
other mode's key set is, so neither mode is only described in prose.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness import build_harness_env
from orchestrator.infrastructure.harness.claude.adapter import (
    SUBSCRIPTION_KEY_HEADER,
    claude_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.registry import ALIASES, SUBSCRIPTION_ALIASES
from orchestrator.infrastructure.settings import Settings

NOW = datetime(2026, 9, 8, tzinfo=UTC)

#: A contract as `env.py::_contract` builds one — the names the aliases are derived from.
CONTRACT = {
    "ORCH_RUN_ID": "01998f0e-0000-7000-8000-000000000001",
    "ORCH_ATTEMPT_ID": "01998f0e-0000-7000-8000-000000000002",
    "ORCH_STORY_ID": "5-4",
    "ORCH_HARNESS": "claude",
    "ORCH_PROJECT": "acme",
    "ORCH_TAGS": "run:r,attempt:a,story:5-4,harness:claude,project:acme",
    "ORCH_LANGFUSE_TAGS": '["run:r", "attempt:a"]',
    "TRACEPARENT": "00-trace-span-01",
    "LITELLM_BASE_URL": "http://gateway:4000",
    "LITELLM_API_KEY": "sk-virtual-key-for-a-test",
    "LANGFUSE_BASE_URL": "http://langfuse:3000",
    "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
    "LANGFUSE_SECRET_KEY": "sk-lf-test",
    "LANGFUSE_ENVIRONMENT": "mvp",
    "ORCH_LOG_CONTENT": "0",
}


def header_lines(aliases: dict[str, str]) -> dict[str, str]:
    """`ANTHROPIC_CUSTOM_HEADERS` is one string of `Name: value` lines; read it back."""
    raw = aliases["ANTHROPIC_CUSTOM_HEADERS"]
    return dict(line.split(": ", 1) for line in raw.split("\n"))


def an_attempt() -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=1,
        status="running",
        harness="claude",
        model="claude-opus-5",
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
        created_at=NOW,
    )


def env_with(settings: Settings) -> dict[str, str]:
    attempt = an_attempt()
    return build_harness_env(settings)(
        attempt,
        run=a_run(attempt),
        project_slug="acme",
        project_env={"MY_FLAG": "on"},
        log_content=False,
        story_id="5-4",
        traceparent="00-trace-span-01",
    )


@pytest.fixture
def subscription(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    return Settings()


@pytest.fixture
def api_key(env: dict[str, str]) -> Settings:
    """The contract's own value — `.env.example` ships the flag off."""
    return Settings()


# ── the alias builder itself ──────────────────────────────────────────────────────────────


def test_the_token_the_subscription_would_override_is_absent() -> None:
    """The whole mechanism. `ANTHROPIC_AUTH_TOKEN` set is `Authorization` overridden, and an
    overridden `Authorization` is the OAuth token never reaching Anthropic."""
    assert "ANTHROPIC_AUTH_TOKEN" not in claude_subscription_aliases(CONTRACT)


def test_the_virtual_key_moves_to_the_header_litellm_reads_it_from() -> None:
    headers = header_lines(claude_subscription_aliases(CONTRACT))

    assert headers[SUBSCRIPTION_KEY_HEADER] == f"Bearer {CONTRACT['LITELLM_API_KEY']}"


def test_the_key_header_is_the_name_litellm_documents() -> None:
    assert SUBSCRIPTION_KEY_HEADER == "x-litellm-api-key"


def test_the_five_attribution_headers_are_still_all_there() -> None:
    """Subscription mode changes who authenticates, not how spend and traces are attributed
    (AD-11): the same five lines, carrying the same contract values."""
    subscription = header_lines(claude_subscription_aliases(CONTRACT))
    default = header_lines(claude_aliases(CONTRACT))

    for header, value in default.items():
        assert subscription[header] == value


def test_it_adds_exactly_one_header_to_the_default_set() -> None:
    added = set(header_lines(claude_subscription_aliases(CONTRACT))) - set(
        header_lines(claude_aliases(CONTRACT))
    )

    assert added == {SUBSCRIPTION_KEY_HEADER}


def test_the_key_it_carries_is_the_virtual_one_and_never_the_spend_key() -> None:
    """AD-5: `LITELLM_SPEND_KEY` reads `/spend/logs/v2` and is the backend's alone. It is not
    in the contract, so the only key this builder can reach is the right one — asserted
    rather than assumed, because this header is new and it takes a key."""
    aliases = claude_subscription_aliases(CONTRACT)

    assert "LITELLM_SPEND_KEY" not in CONTRACT
    assert CONTRACT["LITELLM_API_KEY"] in aliases["ANTHROPIC_CUSTOM_HEADERS"]


def test_content_logging_is_switched_the_same_way_in_both_modes() -> None:
    asked = {**CONTRACT, "ORCH_LOG_CONTENT": "1"}

    subscription = claude_subscription_aliases(asked)

    assert subscription["OTEL_LOG_USER_PROMPTS"] == "1"
    assert subscription["OTEL_LOG_TOOL_CONTENT"] == "1"


def test_content_logging_stays_off_when_the_project_did_not_ask() -> None:
    assert "OTEL_LOG_USER_PROMPTS" not in claude_subscription_aliases(CONTRACT)


# ── the default mode is untouched ─────────────────────────────────────────────────────────


def test_the_default_table_is_not_the_subscription_one() -> None:
    assert ALIASES == {"claude": claude_aliases}
    assert SUBSCRIPTION_ALIASES == {"claude": claude_subscription_aliases}


def test_the_flag_is_off_in_the_shipped_contract(api_key: Settings) -> None:
    """`.env.example` is the configuration contract (AD-20). API-key mode is the default,
    and an operator opts into the other one deliberately."""
    assert api_key.claude_subscription_auth is False


def test_with_the_flag_off_the_environment_still_carries_the_token(api_key: Settings) -> None:
    built = env_with(api_key)

    assert built["ANTHROPIC_AUTH_TOKEN"] == built["LITELLM_API_KEY"]
    assert SUBSCRIPTION_KEY_HEADER not in built["ANTHROPIC_CUSTOM_HEADERS"]


# ── the flag reaches the environment a harness actually receives ──────────────────────────


def test_with_the_flag_on_the_environment_drops_the_token(subscription: Settings) -> None:
    built = env_with(subscription)

    assert "ANTHROPIC_AUTH_TOKEN" not in built


def test_with_the_flag_on_the_environment_carries_the_key_header(subscription: Settings) -> None:
    built = env_with(subscription)

    assert (
        f"{SUBSCRIPTION_KEY_HEADER}: Bearer {built['LITELLM_API_KEY']}"
        in (built["ANTHROPIC_CUSTOM_HEADERS"])
    )


def test_the_key_set_is_the_default_one_minus_the_token(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deviation from `scripts/harness/claude.sh`'s array, stated as an equality.

    One name, and the module docstring says why it is that one. Anything else differing
    between the two modes is a mistake, and this is what would catch it.

    Both `Settings` are built here rather than taken as the two fixtures above, because each
    reads the flag out of the environment at construction: requesting both fixtures in one
    test would have whichever ran second read the value the first had already set.
    """
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "false")
    default = env_with(Settings())
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    subscription = env_with(Settings())

    assert set(default) - set(subscription) == {"ANTHROPIC_AUTH_TOKEN"}
    assert set(subscription) - set(default) == set()


def test_the_gateway_is_still_the_only_base_url_either_mode_talks_to(
    subscription: Settings, env: dict[str, str]
) -> None:
    """Subscription mode is still through the Gateway — that is what makes the spend logs and
    the Langfuse spans exist at all. It authenticates differently; it does not bypass."""
    built = env_with(subscription)

    assert built["LITELLM_BASE_URL"] == env["LITELLM_BASE_URL"]
