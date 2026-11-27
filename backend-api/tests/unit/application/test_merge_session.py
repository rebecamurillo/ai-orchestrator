"""`use_cases/merge_session.py::end_for_resume` (epic 8 story 4, AC6)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.merge_session import end_for_resume
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.merge_world import MERGE, a_parked_merge_world
from tests.unit.application.writer_fixtures import World


def finish(world: World) -> None:
    for turn in [a for a in world.attempts_of(MERGE) if a.role == "session"]:
        world.ports.attempts.update(
            turn.model_copy(update={"status": "done", "ended_at": world.clock.now()})
        )


def end(world: World, kind: str = "continue") -> object:
    return end_for_resume(
        world.ports,
        world.stored_run(),
        world.row(MERGE),
        Signal(kind=kind),  # type: ignore[arg-type]
        "operator",
    )


def test_it_records_the_end_by_the_actor_and_clears_the_flag() -> None:
    world = a_parked_merge_world()
    finish(world)

    run = end(world)

    assert run.senior_session is False  # type: ignore[attr-defined]
    ended = [r for r in world.records() if r.event == "session_end"]
    assert [(r.actor, r.path) for r in ended] == [("operator", MERGE)]
    assert world.stored_run().senior_session is False


def test_a_pending_turn_refuses_and_writes_nothing() -> None:
    world = a_parked_merge_world()
    before = world.events()

    with pytest.raises(Conflict, match="turn running"):
        end(world)

    assert world.events() == before
    assert world.stored_run().senior_session is True


def test_other_signals_leave_the_session_alone() -> None:
    world = a_parked_merge_world()

    end(world, "cancel")

    assert world.stored_run().senior_session is True
    assert "session_end" not in world.events()


def test_a_run_without_an_initiative_is_untouched() -> None:
    world = a_parked_merge_world(initiative=False)
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": True}))

    end(world)

    assert world.stored_run().senior_session is True
    assert "session_end" not in world.events()


def test_no_open_session_writes_nothing() -> None:
    world = a_parked_merge_world()
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": False}))

    end(world)

    assert "session_end" not in world.events()


def test_a_stop_naming_no_row_ends_the_session_without_reading_turns() -> None:
    world = a_parked_merge_world()

    run = end_for_resume(world.ports, world.stored_run(), None, Signal(kind="retry"), "operator")

    assert run.senior_session is False
