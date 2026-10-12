"""What an `agent` row hands the harness so an unattended hub Run keeps going.

O-2 and O-4 of `_bmad-output/specs/unattended-hub-run/PLAN.md` (2026-10-12), plus the
interrupted-attempt log: a resumed session keeps the row's declared model and the Run's
remaining budget, a `workdir` dispatch is told the hub worktree root as an extra directory,
and an attempt closed by orphan control still names the log its killed process wrote.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    BUDGET,
    HEAD_SHA,
    MODEL,
    SPEND,
    WORKTREE,
    World,
    a_world,
    an_agent_row,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import a_tail_world, contracted
from tests.unit.fakes.git import FakeGit

WORKDIR = "repos/member"
MEMBER = f"{WORKTREE}/{WORKDIR}"


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


def a_retry_world(**over: object) -> World:
    previous = an_attempt(
        an_agent_row(),
        1,
        status="error",
        session_id="s-previous",
        end_sha=HEAD_SHA,
        start_sha=HEAD_SHA,
    )
    return a_tail_world(previous=previous, **over)  # type: ignore[arg-type]


# ── O-2: a resumed session keeps the model ──────────────────────────────────


def test_a_resumed_session_is_handed_the_rows_declared_model() -> None:
    world = a_retry_world()

    run(world)

    assert world.harness.called("resume")[0]["model"] == MODEL


def test_a_resumed_session_is_handed_the_runs_remaining_budget() -> None:
    world = a_retry_world()

    run(world)

    assert world.harness.called("resume")[0]["budget_usd_remaining"] == BUDGET - SPEND


def test_a_resumed_session_on_a_row_binding_no_model_is_handed_none() -> None:
    world = a_retry_world(with_resolved=contracted(model=""))

    run(world)

    assert world.harness.called("resume")[0]["model"] is None


def test_a_run_with_no_budget_resumes_with_none_remaining() -> None:
    world = a_retry_world()
    world.ctx = _without_budget(world)

    run(world)

    assert world.harness.called("resume")[0]["budget_usd_remaining"] is None


def _without_budget(world: World) -> StepContext:
    environment = world.ctx.ports.run_env
    assert environment is not None and environment.run is not None
    run_ = environment.run.model_copy(update={"budget_usd": None})
    return replace(
        world.ctx, ports=replace(world.ctx.ports, run_env=replace(environment, run=run_))
    )


# ── O-4: a workdir dispatch is told the hub root ────────────────────────────


def a_workdir_git() -> FakeGit:
    return FakeGit(
        heads={MEMBER: [HEAD_SHA, HEAD_SHA], WORKTREE: [HEAD_SHA, HEAD_SHA]},
        statuses={MEMBER: "", WORKTREE: ""},
        changes={MEMBER: (), WORKTREE: ()},
    )


def test_a_workdir_dispatch_adds_the_hub_worktree_root() -> None:
    world = a_tail_world(with_resolved=contracted(workdir=WORKDIR), git=a_workdir_git())

    run(world)

    started = world.harness.called("start")[0]
    assert started["cwd"] == Path(MEMBER)
    assert started["add_dirs"] == (Path(WORKTREE),)


def test_a_root_dispatch_adds_no_directory() -> None:
    world = a_tail_world()

    run(world)

    assert world.harness.called("start")[0]["add_dirs"] == ()


def test_a_resumed_workdir_session_adds_the_hub_worktree_root_too() -> None:
    world = a_retry_world(with_resolved=contracted(workdir=WORKDIR), git=a_workdir_git())

    run(world)

    resumed = world.harness.called("resume")[0]
    assert resumed["cwd"] == Path(MEMBER)
    assert resumed["add_dirs"] == (Path(WORKTREE),)


# ── an interrupted attempt keeps its log ─────────────────────────────────────


def test_an_interrupted_attempt_is_closed_naming_its_own_log() -> None:
    previous = an_attempt(an_agent_row(), 1, pgid=4242)
    world = a_world(previous=previous, git=FakeGit(status=["", ""], head_sha=[HEAD_SHA]))

    run(world)

    closed = world.attempts.attempts[previous.id]
    assert closed.output_ref == "interrupted"
    assert closed.log_path == str(log_path(replace(world.ctx, attempt=previous)))
    assert closed.log_path.endswith(f"-{previous.n}.log")
    assert closed.log_path != str(log_path(world.ctx))
