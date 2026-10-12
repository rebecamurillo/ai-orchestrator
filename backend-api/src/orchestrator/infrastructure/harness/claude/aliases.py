"""The environment names a `claude` process receives beyond the contract (AD-5, AD-11).

`scripts/harness/claude.sh` declares the default set in `HARNESS_ENV_ALIASES`; the
subscription and gateway-off modes are derived from it here so the five attribution headers
cannot drift between modes by being typed twice.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.infrastructure.harness.env import AliasBuilder

#: The five headers every gateway request of an attempt carries (AD-11), in the order
#: `scripts/harness/claude.sh` documents them. `ANTHROPIC_CUSTOM_HEADERS` is one string of
#: `Name: value` lines, so the order is the order a reader of that file sees.
HEADER_SOURCES: tuple[tuple[str, str], ...] = (
    ("langfuse_session_id", "ORCH_RUN_ID"),
    ("langfuse_tags", "ORCH_LANGFUSE_TAGS"),
    ("x-litellm-end-user-id", "ORCH_RUN_ID"),
    ("x-litellm-session-id", "ORCH_ATTEMPT_ID"),
    ("x-litellm-tags", "ORCH_TAGS"),
)

#: Where the Gateway's virtual key travels when `Authorization` is not carrying it.
#:
#: On a Claude subscription, Claude Code puts its own OAuth token in `Authorization` and the
#: Gateway forwards that upstream (`forward_client_headers_to_llm_api`, host-side), so the
#: key LiteLLM authenticates *this instance* with needs a header of its own. This is the one
#: LiteLLM reads it from. It carries `Bearer <key>`, the same shape `Authorization` would.
SUBSCRIPTION_KEY_HEADER = "x-litellm-api-key"

#: The two names Claude Code reads to put prompt and tool content into its OTLP spans. Added
#: only when the Project asked for content logging (`ORCH_LOG_CONTENT == "1"`).
CONTENT_LOGGING_NAMES = ("OTEL_LOG_USER_PROMPTS", "OTEL_LOG_TOOL_CONTENT")


def claude_aliases(contract: Mapping[str, str]) -> dict[str, str]:
    """The harness-native names `scripts/harness/claude.sh` declares, derived from contract.

    `HARNESS_ENV_ALIASES=(ANTHROPIC_AUTH_TOKEN=LITELLM_API_KEY ANTHROPIC_CUSTOM_HEADERS=derived)`
    — the token is the Gateway's virtual key and never an Anthropic one (AD-5), and the
    headers are the five lines AD-11 pins, built from contract values so nothing here reads
    a setting of its own.

    The content-logging pair is not an alias and is not in either script list: it is a
    switch, present only when `ORCH_LOG_CONTENT` says the Project asked for it.
    """
    headers = "\n".join(f"{header}: {contract[name]}" for header, name in HEADER_SOURCES)
    aliases = {
        "ANTHROPIC_AUTH_TOKEN": contract["LITELLM_API_KEY"],
        "ANTHROPIC_CUSTOM_HEADERS": headers,
    }
    if contract.get("ORCH_LOG_CONTENT") == "1":
        aliases.update(dict.fromkeys(CONTENT_LOGGING_NAMES, "1"))
    return aliases


def claude_subscription_aliases(contract: Mapping[str, str]) -> dict[str, str]:
    """`claude_aliases` for an instance whose Claude Code is logged in on a subscription.

    Two edits to the default set, and it is written as two edits — derived from
    `claude_aliases` rather than restated — so the five attribution headers AD-11 pins and
    the content-logging switch cannot come to differ between the modes by being typed twice:

    - `ANTHROPIC_AUTH_TOKEN` is **dropped**. Set, Claude Code sends it as `Authorization`
      instead of the subscription's OAuth token, and the subscription is never used. Its
      absence is the whole mechanism, not an omission.
    - `SUBSCRIPTION_KEY_HEADER` is added, carrying the same virtual key the dropped name
      held. `Authorization` now belongs to the OAuth token, so the key that identifies this
      instance to the Gateway — for the budget, the rate limit and the spend log — moves to
      the header LiteLLM reads it from when `Authorization` is not its own.

    Still the Gateway's virtual key and never an Anthropic one (AD-5): the subscription's
    credential is Claude Code's own, held in `AGENT_HOME`, and never passes through here.

    This is the one place the environment departs from `scripts/harness/claude.sh`'s
    `HARNESS_ENV_ALIASES` array, which states the default; `tests/unit/
    test_harness_env_subscription.py` states this mode's key set as an equality against it.
    """
    aliases = claude_aliases(contract)
    del aliases["ANTHROPIC_AUTH_TOKEN"]
    aliases["ANTHROPIC_CUSTOM_HEADERS"] = "\n".join(
        (
            aliases["ANTHROPIC_CUSTOM_HEADERS"],
            f"{SUBSCRIPTION_KEY_HEADER}: Bearer {contract['LITELLM_API_KEY']}",
        )
    )
    return aliases


def claude_native_aliases(tracing_enabled: bool) -> AliasBuilder:
    """Gateway-off AliasBuilder factory: no ANTHROPIC_AUTH_TOKEN; Langfuse headers when tracing on.

    No LiteLLM proxy — `ANTHROPIC_AUTH_TOKEN` is never set. `claude` reaches Anthropic
    directly; a Project `ANTHROPIC_API_KEY` travels through `env_for`'s Project-variable
    layer (AD-5). `HEADER_SOURCES[:2]` = `langfuse_session_id` + `langfuse_tags` only (no
    LiteLLM headers). Content-logging pair: same `ORCH_LOG_CONTENT == "1"` rule.
    **Gateway-off vs subscription mode.** `CLAUDE_SUBSCRIPTION_AUTH=true` with gateway on
    routes through LiteLLM. With gateway off there is no proxy to read any header;
    `alias_table`'s gateway-off branch short-circuits before the subscription check to
    prevent conflation of the two modes.
    """

    def builder(contract: Mapping[str, str]) -> dict[str, str]:
        aliases: dict[str, str] = {}
        if tracing_enabled:
            headers = "\n".join(
                f"{header}: {contract[name]}" for header, name in HEADER_SOURCES[:2]
            )
            aliases["ANTHROPIC_CUSTOM_HEADERS"] = headers
        if contract.get("ORCH_LOG_CONTENT") == "1":
            aliases.update(dict.fromkeys(CONTENT_LOGGING_NAMES, "1"))
        return aliases

    return builder
