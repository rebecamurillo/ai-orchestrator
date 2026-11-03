"""AD-24: a stop has a number, and an answer naming an earlier one is refused."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.apply_step_result import budget_second_record
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.writers import park_dependents, park_run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import StepStatus
from orchestrator.domain.values import Park, Signal, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, build_run

BUILD = "stories[0].build"
FIRST_STOP = 1
SECOND_STOP = 2


def parked_world(row_status: StepStatus = "blocked", **over: object) -> World:
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: row_status},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="why it stopped",
        park_seq=SECOND_STOP,
        **over,
    )


def answer(world: World, stop: int | None) -> None:
    signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind="answer", payload={"text": "go"}, stop=stop),
    )


def test_a_run_that_never_stopped_is_at_zero() -> None:
    assert build_run("running").park_seq == 0


def test_each_park_takes_the_next_number() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})

    with world.ports.uow:
        park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="one", path=BUILD))
        world.ports.uow.commit()
    assert world.stored_run().park_seq == FIRST_STOP

    world.ports.runs.update(world.stored_run().model_copy(update={"status": "running"}))
    with world.ports.uow:
        park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="two", path=BUILD))
        world.ports.uow.commit()
    assert world.stored_run().park_seq == SECOND_STOP


def test_a_budget_park_on_top_of_a_stop_is_a_new_stop() -> None:
    world = parked_world()
    budget = Park(kind="budget", reason="budget $41.20 / $40.00")
    result = StepResult(status="blocked", gate="liveness", budget_park=budget)

    budget_second_record(world.ports, world.stored_run(), world.row(BUILD), result)

    assert world.stored_run().park_seq == SECOND_STOP + 1


def test_a_dependency_park_is_a_new_stop() -> None:
    predecessor_id = new_id()
    predecessor = build_run("failed", id=predecessor_id)
    world = a_world("queued", EPIC_PLAN, {}, after_run_ids=(predecessor_id,))
    world.ports.runs.add(predecessor)

    with world.ports.uow:
        park_dependents(world.ports, predecessor)
        world.ports.uow.commit()

    assert world.stored_run().park_kind == "dependency"
    assert world.stored_run().park_seq == FIRST_STOP


def test_a_budget_raise_back_to_the_same_stop_keeps_its_number() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: "blocked"},
        park_kind="budget",
        park_path=BUILD,
        park_reason="budget",
        park_seq=SECOND_STOP,
    )

    signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind="budget_raise", payload={"budget_usd": "99"}),
    )

    assert world.stored_run().park_kind == "blocked"
    assert world.stored_run().park_seq == SECOND_STOP


def test_an_answer_naming_the_current_stop_is_applied() -> None:
    world = parked_world()

    answer(world, SECOND_STOP)

    assert world.status_of(BUILD) == "queued"
    assert world.stored_run().status == "running"


def test_an_answer_naming_no_stop_is_applied_as_before() -> None:
    world = parked_world()

    answer(world, None)

    assert world.status_of(BUILD) == "queued"


def test_a_stale_answer_changes_nothing_and_names_the_current_stop() -> None:
    world = parked_world()
    before = world.events()

    with pytest.raises(Conflict) as refused:
        answer(world, FIRST_STOP)

    message = str(refused.value)
    assert str(SECOND_STOP) in message
    assert "blocked" in message
    assert BUILD in message
    assert world.events() == before
    assert world.status_of(BUILD) == "blocked"
    assert world.engine.calls == []


def test_a_stale_stop_on_a_running_run_is_refused_by_number() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, park_seq=SECOND_STOP)
    before = world.events()

    with pytest.raises(Conflict) as refused:
        answer(world, FIRST_STOP)

    assert str(SECOND_STOP) in str(refused.value)
    assert world.events() == before


def test_a_stale_continue_on_a_dependency_park_is_not_enqueued() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {},
        park_kind="dependency",
        park_path=None,
        park_reason="run x ended failed",
        park_seq=SECOND_STOP,
    )
    before = world.events()

    with pytest.raises(Conflict):
        signal_run(
            world.signal_ports,
            world.run.id,
            Signal(kind="continue", stop=FIRST_STOP),
        )

    assert world.stored_run().status == "needs_you"
    assert world.events() == before
    assert world.engine.calls == []
