"""`infrastructure/harness/registry.py`: the registry and the environment builder (AD-2).

Both moved out of `main.py` in 5.4 so that `walker_deps` can build them without importing
the composition root (AD-2). `tests/unit/test_main_harness_registry.py` is frozen and keeps
importing `build_harnesses` from `orchestrator.main`; this module asserts the new home, and
the thing that only exists here — `build_harness_env`, the closure that binds `Settings` and
the alias table so `application/steps/agent.py` can call `HarnessEnv` and know neither.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.harness import Harness as HarnessPort
from orchestrator.infrastructure.harness import ClaudeHarness, build_harness_env, build_harnesses
from orchestrator.infrastructure.harness.claude.adapter import claude_aliases
from orchestrator.infrastructure.harness.env import HARNESS_ENV_CONTRACT
from orchestrator.infrastructure.harness.registry import ALIASES
from orchestrator.infrastructure.settings import Settings
from tests.unit.fakes.process import FakeProcessRunner

NOW = datetime(2026, 9, 8, tzinfo=UTC)
TRACEPARENT = "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"


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


def an_attempt(run: Run, harness: str | None) -> Attempt:
    return Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=new_id(),
        n=1,
        status="running",
        harness=harness,
    )


# ── the registry, in its new home ────────────────────────────────────────────


def test_the_registry_is_built_here_now(env: dict[str, str]) -> None:
    harnesses = build_harnesses(Settings(), FakeProcessRunner())

    assert list(harnesses) == ["claude"]
    assert isinstance(harnesses["claude"], ClaudeHarness)
    assert isinstance(harnesses["claude"], HarnessPort)


def test_the_registry_uses_the_runner_it_is_handed(env: dict[str, str]) -> None:
    """AD-14: one runner, so one object can kill every group this process started."""
    runner = FakeProcessRunner()

    harness = build_harnesses(Settings(), runner)["claude"]

    assert isinstance(harness, ClaudeHarness)
    assert harness.runner is runner


def test_the_alias_table_is_keyed_the_way_the_registry_is(env: dict[str, str]) -> None:
    assert ALIASES == {"claude": claude_aliases}
    assert set(ALIASES) <= set(build_harnesses(Settings(), FakeProcessRunner()))


# ── the environment builder ──────────────────────────────────────────────────


def test_a_claude_attempt_gets_the_contract_and_the_harnesss_own_names(
    env: dict[str, str],
) -> None:
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, "claude"),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id="4-1",
        traceparent=TRACEPARENT,
    )

    for name in HARNESS_ENV_CONTRACT:
        assert name in built, name
    assert built["TRACEPARENT"] == TRACEPARENT
    assert built["ORCH_STORY_ID"] == "4-1"
    assert built["ORCH_PROJECT"] == "acme"
    # the one alias `scripts/harness/claude.sh` declares for the gateway credential
    assert built["ANTHROPIC_AUTH_TOKEN"] == built["LITELLM_API_KEY"]


def test_a_harness_with_no_alias_builder_gets_the_contract_and_nothing_more(
    env: dict[str, str],
) -> None:
    """Epic 7 adds a line to `ALIASES`; until then an unknown name is not a failure."""
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, "codex"),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=False,
        story_id=None,
        traceparent="",
    )

    assert "ANTHROPIC_AUTH_TOKEN" not in built
    assert built["ORCH_HARNESS"] == "codex"
    assert built["ORCH_STORY_ID"] == ""


def test_an_attempt_that_names_no_harness_still_builds_an_environment(
    env: dict[str, str],
) -> None:
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, None),
        run=run,
        project_slug="acme",
        project_env={},
        log_content=True,
        story_id="4-1",
        traceparent="",
    )

    assert built["ORCH_HARNESS"] == ""
    assert built["ORCH_LOG_CONTENT"] == "1"


def test_a_projects_own_variables_travel_but_a_forbidden_name_does_not(
    env: dict[str, str],
) -> None:
    """AD-5's second refusal, reached through the closure the walker actually wires."""
    run = a_run()

    built = build_harness_env(Settings())(
        an_attempt(run, "claude"),
        run=run,
        project_slug="acme",
        project_env={"MY_VAR": "v", "GITHUB_TOKEN": "leak"},
        log_content=False,
        story_id="4-1",
        traceparent="",
    )

    assert built["MY_VAR"] == "v"
    assert "GITHUB_TOKEN" not in built
