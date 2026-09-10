"""`alias_table` merges per harness rather than swapping tables wholesale (AD-5, AD-11, 7.3).

`SUBSCRIPTION_ALIASES` has always documented itself as a per-harness override — "a harness with
no entry here falls back to `ALIASES`" — and until this story the code did something else: it
chose one table or the other and used it alone. The difference was unobservable while `claude`
was the only key in either, which is exactly why it survived to be found here.

**The defect, and what it would have cost.** With `local` in `ALIASES` and a swap, an instance
running `CLAUDE_SUBSCRIPTION_AUTH=true` would have built a `local` attempt's environment from
`SUBSCRIPTION_ALIASES` alone — a table `local` is not in — so `LANGFUSE_BASEURL` and
`LANGFUSE_USER_ID` would simply not be set. The OpenCode Langfuse plugin would still run, still
export, and still succeed; every generation would just arrive keyed to no Run at all. Nothing
would fail: not the dispatch, not the harness, not a gate. Only `attempt_observed` for `local`
would quietly answer `False` forever, and the readiness gate would report a harness that traces
perfectly well as one that does not — for one authentication mode, on one deployment, with no
error anywhere. AD-11 attribution broken silently is the worst shape a bug can take here, and
that is why this suite asserts the mode nobody runs in development as carefully as the default.

The Operator was asked and ruled on 2026-09-10: merge, and do **not** add `local` to
`SUBSCRIPTION_ALIASES` — under the merge that table stays exactly `{"claude": …}`, which is what
`test_harness_env_subscription.py` still asserts, untouched.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.harness.claude.adapter import (
    claude_aliases,
    claude_subscription_aliases,
)
from orchestrator.infrastructure.harness.opencode.adapter import local_aliases
from orchestrator.infrastructure.harness.registry import (
    ALIASES,
    SUBSCRIPTION_ALIASES,
    alias_table,
    build_harness_env,
)
from orchestrator.infrastructure.settings import Settings

NOW = datetime(2026, 9, 10, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
PLUGIN_NAMES = {"LANGFUSE_BASEURL", "LANGFUSE_USER_ID"}


@pytest.fixture
def api_key(env: dict[str, str]) -> Settings:
    """The shipped contract: `.env.example` has the flag off (AD-20)."""
    return Settings()


@pytest.fixture
def subscription(env: dict[str, str], monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    return Settings()


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        status="running",
        budget_usd=Decimal("10.00"),
        created_at=NOW,
    )


def env_for_local(settings: Settings) -> dict[str, str]:
    run = a_run()
    attempt = Attempt(
        id=new_id(), run_id=run.id, step_run_id=new_id(), n=1, status="running", harness="local"
    )
    return build_harness_env(settings)(
        attempt,
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id="7-3",
        traceparent=TRACEPARENT,
    )


# ── the tables themselves ────────────────────────────────────────────────────


def test_the_subscription_table_stays_the_one_harness_it_describes() -> None:
    """The ruling's own condition: merging is what makes `local` reachable in both modes, so
    the second table needs no entry and keeps describing exactly what it is about."""
    assert SUBSCRIPTION_ALIASES == {"claude": claude_subscription_aliases}
    assert "local" not in SUBSCRIPTION_ALIASES


def test_the_static_table_holds_every_harness_that_declares_aliases() -> None:
    assert ALIASES == {"claude": claude_aliases, "local": local_aliases}


# ── the merge, in both modes ─────────────────────────────────────────────────


def test_api_key_mode_uses_the_static_builders(api_key: Settings) -> None:
    table = alias_table(api_key)

    assert table["claude"] is claude_aliases
    assert table["local"] is local_aliases


def test_subscription_mode_overrides_only_the_harness_it_is_about(
    subscription: Settings,
) -> None:
    table = alias_table(subscription)

    assert table["claude"] is claude_subscription_aliases
    assert table["local"] is local_aliases


def test_both_modes_bind_the_same_set_of_harnesses(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each `Settings` is built here rather than through both fixtures, because each reads the
    flag at construction: requesting both would have the second overwrite the first."""
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "false")
    default = alias_table(Settings())
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    subscription = alias_table(Settings())

    assert set(default) == set(subscription)


def test_codex_is_still_bound_by_the_instance_table_in_both_modes(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`codex_aliases` is a factory over `AGENT_HOME`, so it is bound per instance and the
    merge must not have displaced it in either mode."""
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "false")
    assert "codex" in alias_table(Settings())
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    assert "codex" in alias_table(Settings())


# ── the environment a local process actually receives, in both modes ─────────


def test_a_local_attempt_is_keyed_to_its_run_in_api_key_mode(api_key: Settings) -> None:
    built = env_for_local(api_key)

    assert PLUGIN_NAMES <= set(built)
    assert built["LANGFUSE_USER_ID"] == built["ORCH_RUN_ID"]


def test_a_local_attempt_is_keyed_to_its_run_in_subscription_mode_too(
    subscription: Settings,
) -> None:
    """The regression this module exists for. Before the merge this environment carried
    neither name, and nothing anywhere would have said so."""
    built = env_for_local(subscription)

    assert PLUGIN_NAMES <= set(built)
    assert built["LANGFUSE_USER_ID"] == built["ORCH_RUN_ID"]
    assert built["LANGFUSE_BASEURL"] == built["LANGFUSE_BASE_URL"]


def test_a_local_attempts_environment_is_the_same_in_both_modes(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """How Claude Code authenticates is nothing to do with OpenCode, so the key set of a
    `local` process must not vary with that flag at all."""
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "false")
    default = env_for_local(Settings())
    monkeypatch.setenv("CLAUDE_SUBSCRIPTION_AUTH", "true")
    subscription = env_for_local(Settings())

    assert set(default) == set(subscription)


def test_subscription_mode_still_drops_claudes_token(subscription: Settings) -> None:
    """The merge must not have re-introduced the one name subscription mode exists to remove:
    `ANTHROPIC_AUTH_TOKEN` set is the OAuth login never reaching Anthropic."""
    run = a_run()
    attempt = Attempt(
        id=new_id(), run_id=run.id, step_run_id=new_id(), n=1, status="running", harness="claude"
    )

    built = build_harness_env(subscription)(
        attempt,
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id="7-3",
        traceparent=TRACEPARENT,
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in built
