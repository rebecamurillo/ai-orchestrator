"""The harness registry and the environment builder, built where the adapters are (AD-2).

Both of these were `main.py`'s until 5.4, and both moved for the same reason: the walker's
`StepPorts` are assembled in `infrastructure/dbos/startup.py`, which may not import the
composition root (AD-2), and `main.py` had no room to grow the plumbing that would have
threaded them through `build_engine`. They live beside the adapter each of them names
instead, and `main.py` re-exports `build_harnesses` so the name it was reachable under
stays reachable there.

`ALIASES` is the second half of AD-5's split. `env.py` builds the contract every harness
receives and knows no harness-native name; each adapter supplies an `AliasBuilder` that
turns that contract into its own names. The table below is the one place the two are
joined, so Epic 7's `codex` and `local` adapters add a line here and change nothing else —
and a harness with no entry gets the contract and no aliases, which is exactly what a
harness that declares none should receive.
"""

from __future__ import annotations

from collections.abc import Mapping

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.harness import (
    Harness,
    HarnessEnv,
    TerminalEnv,
    TerminalEnvironment,
)
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.infrastructure.harness.claude import (
    ClaudeHarness,
    claude_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.codex import CodexHarness, codex_aliases
from orchestrator.infrastructure.harness.env import (
    IDENTIFIER_NAMES,
    AliasBuilder,
    env_for,
    terminal_contract,
)
from orchestrator.infrastructure.harness.fake import FakeHarness
from orchestrator.infrastructure.settings import Settings

#: The harness-native name builders, keyed the way the registry itself is (AD-5, AD-10).
ALIASES: dict[str, AliasBuilder] = {ClaudeHarness.name: claude_aliases}

#: The same table for an instance authenticating on a Claude subscription
#: (`CLAUDE_SUBSCRIPTION_AUTH`). A second table rather than a setting read inside
#: `claude_aliases`: the builder's signature is `AliasBuilder`, which takes the contract and
#: nothing else, and that is what keeps `env.py` harness-agnostic and lets
#: `test_harness_env_contract.py` compare a builder against the bash arrays by calling it.
#: A harness with no entry here falls back to `ALIASES` — Epic 7's `codex` and `local` reach
#: LiteLLM by `env_key` and a config file, so neither has an `Authorization` header of
#: Claude's kind to displace, and neither needs a second builder to get one.
SUBSCRIPTION_ALIASES: dict[str, AliasBuilder] = {ClaudeHarness.name: claude_subscription_aliases}


def alias_table(settings: Settings) -> dict[str, AliasBuilder]:
    """The alias builders this instance uses: the static tables, plus the ones a setting binds.

    Two joins in one place, and they are different in kind. Which of `ALIASES` /
    `SUBSCRIPTION_ALIASES` applies is the *instance's* choice of how its Claude Code
    authenticates (`CLAUDE_SUBSCRIPTION_AUTH`), which cannot differ between two attempts of the
    same process. `codex` is in neither table, because its one native name is `CODEX_HOME` and
    the value is `AGENT_HOME`'s — an `AliasBuilder` takes the contract and nothing else (AD-5),
    so `codex_aliases` is a factory and the path is bound here, once, where `Settings` is
    already in hand.

    That is also why the static tables stay claude-only rather than growing a `codex` line: a
    builder that needed a setting could not be stated as a module-level constant without
    reading one inside itself, which is exactly the coupling `AliasBuilder`'s signature exists
    to prevent.
    """
    table = SUBSCRIPTION_ALIASES if settings.claude_subscription_auth else ALIASES
    return {**table, CodexHarness.name: codex_aliases(settings.agent_home)}


def build_harnesses(settings: Settings, runner: ProcessRunner) -> dict[str, Harness]:
    """The harness registry, keyed by the name a Template writes (AD-10).

    The one place an adapter class is named. 5.4's `agent` executor looks a harness up by
    `with_resolved.harness`, so a key here is what makes `harness: claude` in a Template
    resolve to anything at all, and every key is a name `seed_harness_table` also seeds —
    a registry entry with no row would be a harness pre-flight could never enable.

    It takes the `ProcessRunner` rather than building one, because AD-14 wants every harness
    process in a group the same runner can kill: the walker's runner is that one, and
    `walker_deps` passes the very instance it puts on `StepPorts.process`.

    The scripted `fake` harness (AR-14, SPEC CAP-1) is the one conditional entry, and the
    condition is a setting rather than a name a Template may write: with `ORCH_TEST_MODE`
    off it is absent here *and* has no `harness` row, so `harness: fake` resolves to nothing
    and pre-flight refuses it before a Run is created. That is what let the shipped
    Templates keep their `values: [claude, codex, local]` byte for byte — an Operator is
    never offered a harness that only exists to make the gates deterministic.
    """
    built: dict[str, Harness] = {
        ClaudeHarness.name: ClaudeHarness(runner, settings),
        CodexHarness.name: CodexHarness(runner, settings),
    }
    if settings.orch_test_mode:
        built[FakeHarness.name] = FakeHarness(runner, settings)
    return built


def build_harness_env(settings: Settings) -> HarnessEnv:
    """`env_for` with the instance's settings and the alias table already bound (AD-5).

    A closure rather than a partial so the result is the `HarnessEnv` port exactly:
    `application/steps/agent.py` calls it with the facts one attempt has and nothing it
    would have to know about `Settings` to supply.

    The alias table is chosen once, here, because the choice is the instance's and not the
    attempt's: `CLAUDE_SUBSCRIPTION_AUTH` describes how *this deployment's* Claude Code is
    logged in, which cannot differ between two attempts of the same process.
    """
    table = alias_table(settings)

    def harness_env(  # noqa: PLR0913 — the port's own signature
        attempt: Attempt,
        *,
        run: Run,
        project_slug: str,
        project_env: Mapping[str, str],
        log_content: bool,
        story_id: str | None,
        traceparent: str,
    ) -> dict[str, str]:
        return env_for(
            attempt,
            run=run,
            project_slug=project_slug,
            project_env=project_env,
            log_content=log_content,
            settings=settings,
            story_id=story_id,
            traceparent=traceparent,
            aliases=table.get(attempt.harness or ""),
        )

    return harness_env


def build_terminal_env(settings: Settings) -> TerminalEnv:
    """`terminal_contract` with the same alias table `build_harness_env` binds (AD-5, FR-21).

    The whole point of routing the terminal command through the *same* `AliasBuilder` is that
    the export list it prints is the harness's own `HARNESS_ENV_ALIASES` by construction —
    `tests/unit/test_harness_env_contract.py` already holds that builder against the bash
    array, so a name added to `scripts/harness/claude.sh` and not to `claude_aliases` fails
    there rather than silently going missing from a pasted command.

    What makes it safe to run that builder for a screen is what it is fed: `terminal_contract`
    states every credential as `$NAME`, so `claude_aliases` returns `ANTHROPIC_AUTH_TOKEN` =
    `$LITELLM_API_KEY` and builds `ANTHROPIC_CUSTOM_HEADERS` out of identifiers alone.
    Subscription mode needs no special case for the same reason: its extra header renders
    `x-litellm-api-key: Bearer $LITELLM_API_KEY`.

    The only thing this function reads off `Settings` is `claude_subscription_auth`, a bool.
    It never touches a `SecretStr`, and `tests/unit/test_terminal_command.py` asserts that no
    value of any secret setting occurs in the command it produces.
    """
    table = alias_table(settings)

    def terminal_env(
        attempt: Attempt,
        *,
        run: Run,
        project_slug: str,
        story_id: str | None,
        traceparent: str,
    ) -> TerminalEnvironment:
        contract = terminal_contract(
            attempt,
            run=run,
            project_slug=project_slug,
            story_id=story_id,
            traceparent=traceparent,
        )
        builder = table.get(attempt.harness or "")
        exports: Mapping[str, str] = {} if builder is None else builder(contract)
        return TerminalEnvironment(
            identifiers=tuple((name, contract[name]) for name in IDENTIFIER_NAMES),
            exports=tuple(exports.items()),
        )

    return terminal_env
