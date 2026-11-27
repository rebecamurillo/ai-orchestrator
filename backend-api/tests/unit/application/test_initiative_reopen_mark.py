"""`reopen_mark` (epic 9 story 2): the `auto` Run a reopen cancelled, while the spec round runs."""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.initiative_reopen_mark import ReopenMark, reopen_mark
from orchestrator.application.use_cases.initiative_view_types import Loaded
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_read_world import ReadWorld
from tests.unit.initiative_fixtures import AT

BUILD = 2


def cancel(world: ReadWorld, run_id: Any, **payload: Any) -> None:
    world.records.add(
        GateRecord(
            id=new_id(),
            run_id=run_id,
            at=AT,
            event="cancel",
            actor="operator",
            payload=payload,
        )
    )


def loaded_of(world: ReadWorld, initiative: Any) -> Loaded:
    runs = world.runs.list_for_initiative(initiative.id)
    return Loaded(
        initiative=initiative,
        runs=runs,
        rows={},
        attempts={},
        facts={},
        records={r.id: world.records.list_for_run(r.id) for r in runs},
    )


def reopened(world: ReadWorld, spec_status: str, **payload: Any) -> Loaded:
    initiative = world.initiative(round=2)
    build = world.run(initiative, position=BUILD, status="cancelled", minutes=0)
    cancel(
        world, build.id, **(payload or {"reason": "reopen", "step": "intake", "branch": "created"})
    )
    world.run(initiative, position=0, initiative_round=2, status=spec_status, minutes=5)
    return loaded_of(world, initiative)


def test_a_build_cancelled_by_a_reopen_marks_while_the_spec_round_is_not_done() -> None:
    world = ReadWorld()

    assert reopen_mark(reopened(world, "needs_you")) == ReopenMark(
        BUILD, "build", "intake", "created"
    )


def test_a_done_spec_round_clears_the_mark() -> None:
    assert reopen_mark(reopened(ReadWorld(), "done")) is None


def test_another_cancel_reason_is_not_a_mark() -> None:
    world = ReadWorld()

    assert reopen_mark(reopened(world, "running", reason="operator")) is None


def test_a_cancelled_non_auto_run_is_not_a_mark() -> None:
    world = ReadWorld()
    initiative = world.initiative(round=2)
    merge = world.run(initiative, position=1, status="cancelled")
    cancel(world, merge.id, reason="reopen", step="intake", branch="attached")
    world.run(initiative, position=0, initiative_round=2, status="running", minutes=5)

    assert reopen_mark(loaded_of(world, initiative)) is None


def test_no_spec_run_is_no_mark() -> None:
    world = ReadWorld()
    initiative = world.initiative()

    assert reopen_mark(loaded_of(world, initiative)) is None


def test_a_build_of_another_round_is_not_a_mark() -> None:
    world = ReadWorld()
    initiative = world.initiative(round=3)
    build = world.run(initiative, position=BUILD, status="cancelled")
    cancel(world, build.id, reason="reopen", step="intake", branch="attached")
    world.run(initiative, position=0, initiative_round=3, status="running", minutes=5)

    assert reopen_mark(loaded_of(world, initiative)) is None
