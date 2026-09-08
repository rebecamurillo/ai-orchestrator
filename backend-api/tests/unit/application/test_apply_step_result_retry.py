"""`apply_step_result` applying a `StepResult.retry`: the Template's own bounded re-run.

AD-8 leaves the counting and the re-queue to the writer, not to the executor: the `agent`
kind returns `error` carrying the `Retry` its row declared, and everything that follows —
`retry_count + 1`, the `retry_auto` line the Operator reads, and the row going back to
`queued` — happens here, in the one unit of work that already holds the Run.

The shape is `_redispatch`'s (4.5), and the two are deliberately parallel: a bounded
re-execution is one row write, one gate record and no Run transition (AD-9).
"""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.apply_step_result import RETRIED, apply_step_result
from orchestrator.domain.statuses import InvalidTransition
from orchestrator.domain.values import Park, Retry, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
#: `templates/story.yaml`'s own contract, as `agent_row.py` flattens it onto the row.
RETRY = Retry(prompt="No story file with a terminal status was found.", max=2, resume_session=True)
#: The `build` row of `EPIC_PLAN`.
BUILD_SEQ = 5
#: What the counter reads after a second automatic re-run.
SECOND = 2

RETRYING = StepResult(
    status="error", gate="liveness", reason="unexpected status: draft", retry=RETRY
)


def a_run(retry_count: int = 0) -> World:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    row = world.row(BUILD)
    world.ports.steps.update(row.model_copy(update={"retry_count": retry_count}))
    an_attempt(world, BUILD, n=retry_count + 1)
    return world


def test_a_retry_counts_the_attempt_and_puts_the_row_back_on_the_queue() -> None:
    world = a_run()

    apply_step_result(world.ports, world.run.id, BUILD_SEQ, RETRYING)

    assert world.row(BUILD).retry_count == 1
    assert world.status_of(BUILD) == "queued"
    assert world.stored_run().status == "running"


def test_exactly_one_retry_auto_line_says_which_attempt_this_is_and_why() -> None:
    world = a_run()

    apply_step_result(world.ports, world.run.id, BUILD_SEQ, RETRYING)

    lines = [line for line in world.records() if line.event == "retry_auto"]
    assert len(lines) == 1
    assert lines[0].text == "unexpected status: draft · retry 1/2"
    assert lines[0].text == RETRIED.format(reason="unexpected status: draft", n=1, max=2)
    assert (lines[0].actor, lines[0].path, lines[0].attempt_n) == ("machine", BUILD, 1)


def test_the_counter_continues_from_where_the_row_stood() -> None:
    world = a_run(retry_count=1)

    apply_step_result(world.ports, world.run.id, BUILD_SEQ, RETRYING)

    assert world.row(BUILD).retry_count == SECOND
    line = next(line for line in world.records() if line.event == "retry_auto")
    assert line.text == "unexpected status: draft · retry 2/2"


def test_a_retry_leaves_the_successor_alone() -> None:
    """The row is going to run again; queueing what comes after it would run both."""
    world = a_run()

    apply_step_result(world.ports, world.run.id, BUILD_SEQ, RETRYING)

    assert world.status_of(VERIFY) == "planned"


def test_a_retry_carrying_no_reason_still_writes_a_countable_line() -> None:
    world = a_run()

    apply_step_result(
        world.ports,
        world.run.id,
        BUILD_SEQ,
        StepResult(status="error", gate="liveness", retry=RETRY),
    )

    line = next(line for line in world.records() if line.event == "retry_auto")
    assert line.text == " · retry 1/2"


def test_a_result_that_parks_is_not_a_retry_however_it_was_built() -> None:
    """`route` returns one or the other; a park wins if some later rule ever returns both."""
    world = a_run()

    apply_step_result(
        world.ports,
        world.run.id,
        BUILD_SEQ,
        RETRYING.model_copy(update={"park": Park(kind="misconfigured", reason="no story file")}),
    )

    assert world.stored_run().status == "needs_you"
    assert world.status_of(BUILD) == "error"
    assert world.row(BUILD).retry_count == 0


def test_a_retry_on_a_row_that_did_not_reach_error_is_refused_by_the_machine() -> None:
    """AD-8: `("error", "retry")` is the only pair that re-queues; nothing else may."""
    world = a_run()

    with pytest.raises(InvalidTransition):
        apply_step_result(
            world.ports,
            world.run.id,
            BUILD_SEQ,
            StepResult(status="done", gate="liveness", retry=RETRY),
        )


def test_a_result_with_no_retry_at_all_is_routed_the_way_it_always_was() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    an_attempt(world, BUILD)

    apply_step_result(
        world.ports, world.run.id, BUILD_SEQ, StepResult(status="done", gate="liveness")
    )

    assert world.status_of(BUILD) == "done"
    assert world.status_of(VERIFY) == "queued"
    assert [line for line in world.records() if line.event == "retry_auto"] == []
