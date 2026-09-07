"""`application/use_cases/walk.py`: the rules the durable walker is a loop over.

Everything here runs on the shared fakes and the writer fixtures 4.5 left behind, because
these functions are exactly as much of the walk as does not need an engine: what runs next,
what the executor is handed, and how a Run ends. The engine's own half — that each of these
runs once and survives a restart — is `tests/unit/test_dbos_walker.py` and the e2e stack.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, NO_EXECUTOR, register
from orchestrator.application.use_cases.walk import (
    LATE_CLOSE,
    NOT_PARKED,
    STALLED,
    WalkPorts,
    apply_result,
    attempt_row,
    close_run,
    expire,
    next_row,
    run_row,
)
from orchestrator.application.use_cases.writers import RUN_EXPIRED, Entry, record
from orchestrator.domain.errors import NotFound
from orchestrator.domain.values import Park, StepResult
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

REFERENCE = {"workflow_id": "w-1", "step_id": 3}
WORK_DIR = "/work"

#: The second row of `PAIR_PLAN`, and the second attempt at a row.
SECOND = 2


def ports_of(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
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
    """`plan.check` bound to a recording executor for the length of one test."""
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("plan.check", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


@pytest.fixture
def empty_registry() -> Iterator[dict[str, Any]]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    yield EXECUTORS
    EXECUTORS.clear()
    EXECUTORS.update(kept)


# ── next_row ────────────────────────────────────────────────────────────────


def test_a_created_run_has_its_first_row_queued_and_reported() -> None:
    """Nothing else queues the first row of a plan: the planner writes every row `planned`."""
    world = a_world("queued", PAIR_PLAN)

    seq = next_row(ports_of(world), world.run.id)

    assert seq == 1
    assert world.status_of("plan") == "queued"
    assert world.ports.uow.committed


def test_a_queued_row_is_taken_as_it_stands() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "queued"})

    assert next_row(ports_of(world), world.run.id) == SECOND
    assert world.status_of("checkout") == "queued"


def test_a_run_stopped_on_a_row_queues_nothing_ahead_of_it() -> None:
    """A parked Run has `planned` rows further down; running one would pass the stop."""
    world = a_world("needs_you", PAIR_PLAN, {"plan": "error"}, park_kind="internal")

    assert next_row(ports_of(world), world.run.id) is None
    assert world.status_of("checkout") == "planned"


def test_a_run_whose_rows_are_all_finished_has_nothing_to_run() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "skipped"})

    assert next_row(ports_of(world), world.run.id) is None


def test_the_first_planned_row_is_taken_even_when_earlier_rows_were_skipped() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "skipped"})

    assert next_row(ports_of(world), world.run.id) == SECOND


# ── attempt_row ─────────────────────────────────────────────────────────────


def test_the_row_starts_and_its_executor_runs(executor: Recording) -> None:
    world = a_world("queued", PAIR_PLAN, {"plan": "queued"})

    result = attempt_row(ports_of(world), world.run.id, 1, REFERENCE)

    assert result.status == "done"
    assert world.status_of("plan") == "running"
    assert [attempt.n for attempt in world.attempts_of("plan")] == [1]
    assert world.attempts_of("plan")[0].engine_ref == REFERENCE


def test_a_kind_with_no_executor_stops_the_run_with_the_reason(
    empty_registry: dict[str, Any],
) -> None:
    world = a_world("queued", PAIR_PLAN, {"plan": "queued"})

    result = attempt_row(ports_of(world), world.run.id, 1, REFERENCE)

    assert result.park is not None
    assert result.park.reason == NO_EXECUTOR.format(kind="plan.check")


def test_re_running_an_interrupted_row_closes_its_attempt_and_opens_the_next(
    executor: Recording,
) -> None:
    """The restart case: the durable step re-executes, so the row gets Attempt 2 (FR-12)."""
    world = a_world("running", PAIR_PLAN, {"plan": "queued"})
    attempt_row(ports_of(world), world.run.id, 1, REFERENCE)

    attempt_row(ports_of(world), world.run.id, 1, REFERENCE)

    attempts = world.attempts_of("plan")
    assert [attempt.n for attempt in attempts] == [1, 2]
    assert attempts[0].status == "error"
    assert attempts[0].ended_at is not None
    assert attempts[1].ended_at is None
    assert world.status_of("plan") == "running"


# ── run_row: the context AD-9 describes ─────────────────────────────────────


def test_the_executor_is_handed_the_row_the_planner_resolved(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, {"plan": {"command": "true"}})
    an_attempt(world, "plan")

    run_row(ports_of(world), world.run.id, 1)

    context = executor.seen[0]
    assert context.row.path == "plan"
    assert context.with_resolved == {"command": "true"}
    assert context.ports.work_dir == WORK_DIR


def test_the_context_carries_the_run_s_worktree_and_the_previous_attempt(
    executor: Recording,
) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, worktree_path="/work/wt/a")
    an_attempt(world, "plan", n=1, ended_at=EPOCH, status="error")
    an_attempt(world, "plan", n=2)

    run_row(ports_of(world), world.run.id, 1)

    context = executor.seen[0]
    assert context.cwd == "/work/wt/a"
    assert context.attempt.n == SECOND
    assert context.previous_attempt is not None
    assert context.previous_attempt.n == 1


def test_a_row_inside_a_frame_carries_the_commit_that_frame_started_at(
    executor: Recording,
) -> None:
    world = a_world("running", statuses={"stories[0].build": "running"})
    an_attempt(world, "stories[0].sync", n=1, start_sha="a" * 40, ended_at=EPOCH, status="done")
    an_attempt(world, "stories[0].build", n=1)
    seq = world.row("stories[0].build").seq
    register("agent", executor)

    run_row(ports_of(world), world.run.id, seq)

    assert executor.seen[0].frame_start_sha == "a" * 40


def test_a_row_outside_a_frame_has_no_frame_commit(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")

    run_row(ports_of(world), world.run.id, 1)

    assert executor.seen[0].frame_start_sha is None


def test_the_resumed_row_reads_the_record_the_signal_wrote(executor: Recording) -> None:
    """AD-9: the worktree effects of a signal happen in the resumed row's executor."""
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")
    signal_run_record(world)

    run_row(ports_of(world), world.run.id, 1, "answer")

    resumed = executor.seen[0].resume_signal
    assert resumed is not None
    assert resumed.event == "answer"
    assert resumed.text == "the answer"


def test_a_row_that_was_not_resumed_has_no_signal(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")
    signal_run_record(world)

    run_row(ports_of(world), world.run.id, 1)

    assert executor.seen[0].resume_signal is None


def test_a_signal_kind_with_no_record_reads_as_none(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")

    run_row(ports_of(world), world.run.id, 1, "retry")

    assert executor.seen[0].resume_signal is None


def test_a_row_with_no_attempt_is_a_walker_bug_and_says_so(executor: Recording) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})

    with pytest.raises(NotFound, match="no attempt"):
        run_row(ports_of(world), world.run.id, 1)


def signal_run_record(world: World) -> None:
    """One `answer` record, as `signal_run` would have appended it."""
    record(world.ports, world.run, Entry(event="answer", actor="operator", text="the answer"))


# ── apply_result, close_run, expire ─────────────────────────────────────────


def test_apply_result_reports_where_the_run_now_stands() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")

    status = apply_result(
        ports_of(world),
        world.run.id,
        1,
        StepResult(status="error", gate="deterministic", park=Park(kind="timeout", reason="t")),
    )

    assert status == "needs_you"


def test_a_run_whose_rows_all_finished_ends_done() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "skipped"})

    assert close_run(ports_of(world), world.run.id) == "done"
    assert world.events() == ["done"]


def test_a_run_with_nothing_runnable_left_parks_internal_naming_the_row() -> None:
    """`on_fail: escalate` and a `blocked` row with no signal both land here (AD-9)."""
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "error"})

    assert close_run(ports_of(world), world.run.id) == "needs_you"
    stored = world.stored_run()
    assert stored.park_kind == "internal"
    assert stored.park_path == "checkout"
    assert stored.park_reason == STALLED.format(path="checkout", status="error")


def test_the_thirty_day_wait_ends_the_run_failed() -> None:
    world = a_world("needs_you", PAIR_PLAN, {"plan": "checkpoint"}, park_kind="checkpoint")

    assert expire(ports_of(world), world.run.id) == "failed"
    stored = world.stored_run()
    assert stored.ended_at is not None
    assert stored.park_kind is None
    assert world.records()[-1].text == RUN_EXPIRED
    assert world.records()[-1].event == "failed"


def test_an_expiry_a_signal_beat_writes_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("info")
    world = a_world("running", PAIR_PLAN, {"plan": "queued"})

    assert expire(ports_of(world), world.run.id) == "running"
    assert world.records() == []
    assert NOT_PARKED in capsys.readouterr().out


def test_a_frame_whose_rows_have_not_run_yet_has_no_commit(executor: Recording) -> None:
    """The first row of a frame is the one being started: nothing in it has an attempt."""
    world = a_world("running", statuses={"stories[0].sync": "running"})
    an_attempt(world, "stories[0].sync", n=1)
    seq = world.row("stories[0].sync").seq
    register("git.sync", executor)

    run_row(ports_of(world), world.run.id, seq)

    assert executor.seen[0].frame_start_sha is None


def test_a_frame_reads_past_a_row_that_never_ran_to_the_one_that_did(
    executor: Recording,
) -> None:
    world = a_world("running", statuses={"stories[0].build": "running"})
    an_attempt(world, "stories[0].build", n=1, start_sha="b" * 40)
    seq = world.row("stories[0].build").seq
    register("agent", executor)

    run_row(ports_of(world), world.run.id, seq)

    assert executor.seen[0].frame_start_sha == "b" * 40


def test_an_interrupted_attempt_that_had_already_ended_is_left_alone(
    executor: Recording,
) -> None:
    """A row found `running` whose Attempt closed is a re-walk, not an interruption."""
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan", n=1, status="error", ended_at=EPOCH)

    attempt_row(ports_of(world), world.run.id, 1, REFERENCE)

    attempts = world.attempts_of("plan")
    assert [attempt.n for attempt in attempts] == [1, SECOND]
    assert attempts[0].ended_at == EPOCH


def test_a_close_that_arrives_after_the_run_moved_writes_nothing(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`cancel` can move the Run while a step is in flight; both endings would raise."""
    configure_logging("info")
    world = a_world("cancelled", PAIR_PLAN, {"plan": "skipped", "checkout": "skipped"})

    assert close_run(ports_of(world), world.run.id) == "cancelled"
    assert world.records() == []
    assert LATE_CLOSE in capsys.readouterr().out
