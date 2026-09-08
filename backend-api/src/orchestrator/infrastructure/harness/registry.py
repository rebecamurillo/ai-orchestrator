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
from orchestrator.domain.ports.harness import Harness, HarnessEnv
from orchestrator.domain.ports.process import ProcessRunner
from orchestrator.infrastructure.harness.claude import (
    ClaudeHarness,
    claude_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.env import AliasBuilder, env_for
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


def build_harnesses(settings: Settings, runner: ProcessRunner) -> dict[str, Harness]:
    """The harness registry, keyed by the name a Template writes (AD-10).

    The one place an adapter class is named. 5.4's `agent` executor looks a harness up by
    `with_resolved.harness`, so a key here is what makes `harness: claude` in a Template
    resolve to anything at all, and every key is a name `seed_harness_table` also seeds —
    a registry entry with no row would be a harness pre-flight could never enable.

    It takes the `ProcessRunner` rather than building one, because AD-14 wants every harness
    process in a group the same runner can kill: the walker's runner is that one, and
    `walker_deps` passes the very instance it puts on `StepPorts.process`.
    """
    return {ClaudeHarness.name: ClaudeHarness(runner, settings)}


def build_harness_env(settings: Settings) -> HarnessEnv:
    """`env_for` with the instance's settings and the alias table already bound (AD-5).

    A closure rather than a partial so the result is the `HarnessEnv` port exactly:
    `application/steps/agent.py` calls it with the facts one attempt has and nothing it
    would have to know about `Settings` to supply.

    The alias table is chosen once, here, because the choice is the instance's and not the
    attempt's: `CLAUDE_SUBSCRIPTION_AUTH` describes how *this deployment's* Claude Code is
    logged in, which cannot differ between two attempts of the same process.
    """
    table = SUBSCRIPTION_ALIASES if settings.claude_subscription_auth else ALIASES

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
