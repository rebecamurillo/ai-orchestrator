"""`budget_second_record` — Epic 5's own `after_route` (5.7): a routed stop that is also
over budget gets a second gate record, and `run.park_kind`/`park_path`/`park_reason` are
rewritten to `budget` on top of it, without a second `run_transition` (`RUN_TRANSITIONS`
has no `(needs_you, "park")` pair). TDD first (AD-18).
"""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import (
    apply_step_result,
    budget_second_record,
)
from orchestrator.application.use_cases.writers import park_run
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world

DONE = StepResult(status="done", gate="deterministic", output_ref="/work/logs/1.log")

BUDGET_PARK = Park(kind="budget", reason="budget $41.20 / $40.00")


def a_pair(**over: object) -> World:
    return a_world("running", PAIR_PLAN, {"plan": "running"}, **over)


def test_no_budget_park_writes_nothing() -> None:
    world = a_pair()
    run = world.stored_run()

    budget_second_record(world.ports, run, world.row("plan"), DONE)

    assert world.events() == []
    assert world.stored_run().park_kind is None


def test_a_budget_park_rewrites_the_run_and_appends_a_second_record() -> None:
    """AD-8's own docstring on `Run`: the three park fields and the gate record are
    written together — this is the second time, on the same Run, without re-entering
    `run_transition` (the Run is already `needs_you`)."""
    world = a_pair()
    row = world.row("plan")
    parked = park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="ask"))
    result = DONE.model_copy(update={"status": "blocked", "budget_park": BUDGET_PARK})

    budget_second_record(world.ports, parked, row, result)

    stored = world.stored_run()
    assert stored.status == "needs_you"
    assert stored.park_kind == "budget"
    assert stored.park_reason == "budget $41.20 / $40.00"
    assert world.events() == ["blocked", "budget"]


def test_the_second_records_path_falls_back_to_the_row() -> None:
    world = a_pair()
    row = world.row("plan")
    parked = park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="ask"))
    result = DONE.model_copy(update={"budget_park": BUDGET_PARK})

    budget_second_record(world.ports, parked, row, result)

    stored = world.stored_run()
    assert stored.park_path == row.path
    assert world.records()[-1].path == row.path


def test_a_budget_parks_own_path_is_kept_when_it_names_one() -> None:
    world = a_pair()
    row = world.row("plan")
    parked = park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="ask"))
    named = Park(kind="budget", reason="budget $1.00 / $0.50", path="elsewhere")
    result = DONE.model_copy(update={"budget_park": named})

    budget_second_record(world.ports, parked, row, result)

    assert world.stored_run().park_path == "elsewhere"


# ── through `apply_step_result`'s own `after_route` seam ────────────────────


def test_a_routed_blocked_result_over_budget_writes_two_records_through_apply_step_result() -> None:
    world = a_pair()
    blocked = StepResult(
        status="blocked",
        gate="deterministic",
        park=Park(kind="blocked", reason="ask", path="plan"),
        budget_park=BUDGET_PARK,
    )

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        blocked,
        after_route=lambda run, row, result: budget_second_record(world.ports, run, row, result),
    )

    assert world.status_of("plan") == "blocked"
    assert world.stored_run().park_kind == "budget"
    assert world.events() == ["blocked", "budget"]


def test_a_routed_done_result_with_a_direct_budget_park_writes_one_record() -> None:
    """The `done` + over-budget shape (5.7's own AC): `park` carries the budget Park
    directly, so `_route` writes the one record and `after_route` has nothing to add."""
    world = a_pair()
    done_over_budget = DONE.model_copy(update={"park": BUDGET_PARK})

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        done_over_budget,
        after_route=lambda run, row, result: budget_second_record(world.ports, run, row, result),
    )

    assert world.status_of("plan") == "done"
    assert world.stored_run().park_kind == "budget"
    assert world.events() == ["budget"]
