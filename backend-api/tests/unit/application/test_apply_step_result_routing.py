"""`apply_step_result`'s `on_fail` routing (AD-9), completed: `continue` beside `fail`.

4.5 landed the `fail` case and left the other two: a row that declared `on_fail: continue`
wrote its status and then queued nothing, so the Run stopped with no reason anywhere. The
walker is what made that visible — its loop asks for the next row, and a Run with nothing
queued and rows left is a stall — so this is the story that closes it.

`escalate`, the action the DSL gives a row that declared none, is deliberately still not
routed here: an executor that escalates returns the `Park` that says why, and a row that
somehow reaches `error` with no park at all is reported by `walk.close_run` as an `internal`
park naming the row (`tests/unit/application/test_walk_use_case.py`), which is a stated
outcome rather than a silent stall.
"""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world, an_attempt

FAILED = StepResult(status="error", gate="deterministic", reason="exit 1")


def a_run(action: str | None) -> object:
    resolved = {"plan": {"on_fail": action}} if action is not None else {"plan": {}}
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, resolved)
    an_attempt(world, "plan")
    return world


def test_continue_queues_the_successor_exactly_as_a_finished_row_does() -> None:
    world = a_run("continue")

    apply_step_result(world.ports, world.run.id, 1, FAILED)

    assert world.status_of("plan") == "error"
    assert world.status_of("checkout") == "queued"
    assert world.stored_run().status == "running"


def test_continue_on_the_last_row_ends_the_run_done() -> None:
    """The row failed and the Template said to carry on; there is nothing left to carry to."""
    world = a_world(
        "running",
        PAIR_PLAN,
        {"plan": "done", "checkout": "running"},
        {"checkout": {"on_fail": "continue"}},
    )
    an_attempt(world, "checkout")

    apply_step_result(world.ports, world.run.id, 2, FAILED)

    assert world.stored_run().status == "done"


def test_continue_keeps_the_rows_own_reason_on_it() -> None:
    """`continue` decides where the Run goes next, not whether the step succeeded."""
    world = a_run("continue")

    apply_step_result(world.ports, world.run.id, 1, FAILED)

    assert world.row("plan").reason == "exit 1"


def test_fail_still_ends_the_run_failed() -> None:
    world = a_run("fail")

    apply_step_result(world.ports, world.run.id, 1, FAILED)

    assert world.stored_run().status == "failed"


def test_escalate_writes_the_row_and_leaves_the_run_running() -> None:
    world = a_run("escalate")

    apply_step_result(world.ports, world.run.id, 1, FAILED)

    assert world.status_of("plan") == "error"
    assert world.status_of("checkout") == "planned"
    assert world.stored_run().status == "running"


def test_a_row_that_declared_no_routing_is_treated_as_escalate() -> None:
    world = a_run(None)

    apply_step_result(world.ports, world.run.id, 1, FAILED)

    assert world.stored_run().status == "running"
    assert world.status_of("checkout") == "planned"
