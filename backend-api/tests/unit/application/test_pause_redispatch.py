"""Story 2-1, review fix: a pause that lands after a redispatch names the row that runs next.

After a verify failure sends the Run back, the row finishing is the redispatch target. Its
successor in plan order may be a row that is already `done`, while the walker's next row is the
verify row that failed (`walk._sent_back`). The stop must name that one."""

from __future__ import annotations

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.pause_stop import PAUSED_REASON
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.walk import WalkPorts, next_row
from orchestrator.domain.values import Signal, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

SYNC = "stories[0].sync"
BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
DONE = StepResult(status="done", gate="deterministic")


def redispatched(target: str) -> World:
    """verify failed and sent the Run back to `target`, which is now running."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {SYNC: "done", BUILD: "done", VERIFY: "error", target: "running"},
        pause_requested=True,
    )
    aim = {"on_fail": {"target_seq": world.row(target).seq, "max": 2}}
    world.ports.steps.update(world.row(VERIFY).model_copy(update={"with_resolved": aim}))
    an_attempt(world, target)
    return world


def land(world: World, target: str) -> None:
    apply_step_result(world.ports, world.run.id, world.row(target).seq, DONE)


def test_a_redispatch_over_done_rows_parks_on_the_verify_row_that_runs_next() -> None:
    world = redispatched(SYNC)

    land(world, SYNC)

    run = world.stored_run()
    assert (run.status, run.park_kind, run.park_path) == ("needs_you", "paused", VERIFY)
    assert run.park_reason == PAUSED_REASON.format(path=VERIFY)
    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"
    assert run.pause_requested is False


def test_a_redispatch_straight_back_to_the_verify_row_names_it_too() -> None:
    world = redispatched(BUILD)

    land(world, BUILD)

    run = world.stored_run()
    assert (run.park_kind, run.park_path) == ("paused", VERIFY)
    assert world.status_of(VERIFY) == "queued"


def test_continue_then_runs_the_row_the_stop_named() -> None:
    world = redispatched(SYNC)
    land(world, SYNC)

    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))

    ports = WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )
    assert next_row(ports, world.run.id) == world.row(VERIFY).seq
    assert world.status_of(BUILD) == "done"


def test_an_ordinary_boundary_still_names_the_queued_successor() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, pause_requested=True)
    an_attempt(world, BUILD)

    land(world, BUILD)

    assert world.stored_run().park_path == VERIFY
    assert world.status_of(VERIFY) == "queued"
