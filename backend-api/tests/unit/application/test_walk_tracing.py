"""`run_row` wraps one row's execution in `tracer.step_span` (AD-11, 5.2's own Scope).

`test_walk_use_case.py` (frozen) proves the "no tracer" row of the matrix: its own
`ports_of` builds `StepPorts(git=..., clock=..., work_dir=...)` with no `tracer` at all, so
`run_row` degrades to "no span opened" exactly as before this story. This file proves the
other row — a wired `FakeTracer` — and re-derives the worktree, previous-attempt and
frame-commit assertions `test_walk_use_case.py` already makes, because `run_row`'s own
`_context` helper changed shape here: it now takes the `Run` the walker already read rather
than re-fetching it, and this is the only file exercising `run_row` end to end with that
change alongside a real span.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.walk import WalkPorts, run_row
from orchestrator.domain.errors import NotFound
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.tracer import FakeTracer

WORK_DIR = "/work"
SECOND = 2


def ports_of(world: World, tracer: FakeTracer) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR, tracer=tracer),
    )


class Recording:
    """An executor that answers `done` and keeps the context it was handed."""

    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("plan.check", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def test_run_row_opens_and_closes_a_step_span_around_execute(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")
    tracer = FakeTracer()

    run_row(ports_of(world, tracer), world.run.id, 1)

    assert tracer.step_span_calls == [(world.run.id, "plan", executor.seen[0].attempt.id)]


def test_run_row_with_no_attempt_still_raises_before_any_span_opens(executor: Recording) -> None:
    """A walker bug is reported before a span is opened, not after — nothing to close."""
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    tracer = FakeTracer()

    with pytest.raises(NotFound, match="no attempt"):
        run_row(ports_of(world, tracer), world.run.id, 1)

    assert tracer.step_span_calls == []


def test_the_executor_still_reads_the_row_the_planner_resolved(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, {"plan": {"command": "true"}})
    an_attempt(world, "plan")
    tracer = FakeTracer()

    run_row(ports_of(world, tracer), world.run.id, 1)

    context = executor.seen[0]
    assert context.row.path == "plan"
    assert context.with_resolved == {"command": "true"}
    assert context.ports.work_dir == WORK_DIR


def test_the_context_still_carries_the_runs_worktree_and_the_previous_attempt(
    executor: Recording,
) -> None:
    """Re-derives the frozen `test_walk_use_case.py` assertion: `_context`'s own refactor
    (the `Run` reused, not re-fetched a second time) changes nothing about this."""
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, worktree_path="/work/wt/a")
    an_attempt(world, "plan", n=1, ended_at=EPOCH, status="error")
    an_attempt(world, "plan", n=2)
    tracer = FakeTracer()

    run_row(ports_of(world, tracer), world.run.id, 1)

    context = executor.seen[0]
    assert context.cwd == "/work/wt/a"
    assert context.attempt.n == SECOND
    assert context.previous_attempt is not None
    assert context.previous_attempt.n == 1


def test_a_row_inside_a_frame_still_carries_the_commit_that_frame_started_at(
    executor: Recording,
) -> None:
    world = a_world("running", statuses={"stories[0].build": "running"})
    an_attempt(world, "stories[0].sync", n=1, start_sha="a" * 40, ended_at=EPOCH, status="done")
    an_attempt(world, "stories[0].build", n=1)
    seq = world.row("stories[0].build").seq
    register("agent", executor)
    tracer = FakeTracer()

    run_row(ports_of(world, tracer), world.run.id, seq)

    assert executor.seen[0].frame_start_sha == "a" * 40
    assert tracer.step_span_calls == [
        (world.run.id, "stories[0].build", executor.seen[0].attempt.id)
    ]
