"""`initiative_advance.record_advance` / `enqueue_advances` and the four writers that call them
(epic 8 story 1, AC1-AC4): a terminal transition of an initiative Run stores one advance in its
own unit of work and hands the id to the engine after the commit."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.initiative_advance import enqueue_advances, record_advance
from orchestrator.application.use_cases.walk import close_run, expire
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from tests.unit.application.test_signal_run import parked, send
from tests.unit.application.test_walk_use_case import ports_of
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.initiatives import FakeInitiativeAdvanceRepository

DONE = StepResult(status="done", gate="deterministic", output_ref="/work/logs/1.log")
FAILED = StepResult(status="error", gate="deterministic", reason="boom")


def wired(world: World) -> FakeInitiativeAdvanceRepository:
    advances = FakeInitiativeAdvanceRepository()
    world.ports = replace(world.ports, advances=advances, engine=world.engine)
    return advances


def initiative_fields() -> dict[str, Any]:
    return {"initiative_id": new_id(), "initiative_round": 2, "initiative_position": 3}


def failing_world(**over: Any) -> World:
    return a_world(
        "running",
        PAIR_PLAN,
        {"plan": "running"},
        with_resolved={"plan": {"on_fail": "fail"}},
        **over,
    )


def done_world(**over: Any) -> World:
    return a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"}, **over)


def step_failed(world: World) -> None:
    apply_step_result(world.ports, world.run.id, 1, FAILED)


def step_done(world: World) -> None:
    apply_step_result(world.ports, world.run.id, 2, DONE)


def expired(world: World) -> None:
    expire(ports_of(world), world.run.id)


def cancelled(world: World) -> None:
    send(world, "cancel", confirm=True)


def signal_done(world: World) -> None:
    send(world, "continue")


Scenario = tuple[Callable[[], World], Callable[[World], None], str]


def scenarios(**over: Any) -> dict[str, Scenario]:
    return {
        "step failed": (lambda: failing_world(**over), step_failed, "failed"),
        "step done": (lambda: done_world(**over), step_done, "done"),
        "close_run": (
            lambda: a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}, **over),
            lambda w: close_run(ports_of(w), w.run.id),
            "done",
        ),
        "expire": (
            lambda: a_world(
                "needs_you", PAIR_PLAN, {"plan": "checkpoint"}, park_kind="checkpoint", **over
            ),
            expired,
            "failed",
        ),
        "cancel signal": (
            lambda: parked("checkpoint", "plan", "checkpoint", plan=PAIR_PLAN, **over),
            cancelled,
            "cancelled",
        ),
        "finishing signal": (
            lambda: parked(
                "checkpoint", "after", "checkpoint", plan=(("after", "checkpoint"),), **over
            ),
            signal_done,
            "done",
        ),
    }


@pytest.mark.parametrize("name", list(scenarios()))
def test_ac1_ac2_every_terminal_writer_stores_one_advance_then_enqueues_it(name: str) -> None:
    build, act, status = scenarios(**initiative_fields())[name]
    world = build()
    advances = wired(world)

    act(world)

    run = world.stored_run()
    assert run.status == status
    [advance] = advances.advances
    assert advance.initiative_id == run.initiative_id
    assert (advance.from_run_id, advance.round, advance.position) == (run.id, 2, 3)
    assert advance.blocked_reason is None
    assert advance.consumed_at is None
    enqueued = [call for call in world.engine.calls if call[0] == "enqueue_advance"]
    assert enqueued == [("enqueue_advance", advance.id)]
    index = [call[0] for call in world.engine.calls].index("enqueue_advance")
    assert world.engine.committed_when_called[index] is True


@pytest.mark.parametrize("name", list(scenarios()))
def test_ac3_a_run_without_an_initiative_stores_and_enqueues_nothing(name: str) -> None:
    build, act, _ = scenarios()[name]
    world = build()
    advances = wired(world)

    act(world)

    assert advances.advances == []
    assert not [call for call in world.engine.calls if call[0] == "enqueue_advance"]


def test_ac4_a_second_record_for_the_same_key_changes_nothing() -> None:
    world = failing_world(**initiative_fields())
    advances = wired(world)
    step_failed(world)
    before = list(advances.advances)

    record_advance(world.ports, world.stored_run())

    assert advances.advances == before


def test_record_advance_ignores_a_run_that_has_not_ended() -> None:
    world = a_world("running", PAIR_PLAN, **initiative_fields())
    advances = wired(world)

    record_advance(world.ports, world.run)

    assert advances.advances == []


def test_record_advance_without_the_repository_is_a_no_op() -> None:
    world = failing_world(**initiative_fields())

    record_advance(world.ports, world.run.model_copy(update={"status": "failed"}))


def test_enqueue_advances_skips_a_consumed_or_blocked_advance() -> None:
    world = failing_world(**initiative_fields())
    advances = wired(world)
    step_failed(world)
    world.engine.calls.clear()
    [advance] = advances.advances
    run = world.stored_run()

    advances.advances[0] = advance.model_copy(update={"blocked_reason": "x"})
    enqueue_advances(world.engine, world.ports, run)
    advances.advances[0] = advance.model_copy(update={"consumed_at": world.clock.now()})
    enqueue_advances(world.engine, world.ports, run)

    assert world.engine.calls == []


def test_enqueue_advances_without_an_engine_or_repository_does_nothing() -> None:
    world = failing_world(**initiative_fields())
    run = world.run.model_copy(update={"status": "failed"})
    enqueue_advances(None, world.ports, run)
    enqueue_advances(world.engine, world.ports, run)
    wired(world)
    enqueue_advances(
        world.engine, world.ports, world.run.model_copy(update={"initiative_id": None})
    )
    enqueue_advances(world.engine, world.ports, run)

    assert world.engine.calls == []
