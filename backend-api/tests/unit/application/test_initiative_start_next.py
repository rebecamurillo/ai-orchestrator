"""`start_next` (story 5, epic 7, AC6-AC9), on the shared fakes."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases.initiative_start_next import (
    NO_CONVERSATION,
    NOT_FORCEABLE,
    start_next,
)
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from orchestrator.domain.entities.project_package import GateWords, StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.initiative_world import InitiativeWorld
from tests.unit.initiative_fixtures import a_run

SEQ = 3


def decl(name: str, kind: str = "conversation") -> StepDecl:
    return StepDecl(
        id=name,
        kind=kind,
        skill=None,
        persona=None,
        file=None,
        writes=(),  # type: ignore[arg-type]
    )


def sequence() -> FrozenSequence:
    steps = (decl("product"), decl("ux"), decl("tech"), decl("gate", "automatic"))
    return FrozenSequence(
        package="p",
        sha="abc",
        workflows=(
            FrozenWorkflow(
                workflow="spec",
                template="p/spec",
                version=1,
                type="interactive",
                shown_as="workflow",
                steps=steps,
            ),
        ),
        gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
        status_map={},
    )


def parked(
    world: InitiativeWorld, step: str = "product", **overrides: Any
) -> tuple[Initiative, Run]:
    initiative = world.initiative(sequence=sequence())
    values: dict[str, Any] = {
        "project_id": world.project.id,
        "repository_id": world.hub.id,
        "initiative_id": initiative.id,
        "initiative_round": 1,
        "initiative_position": 0,
        "status": "needs_you",
        "park_kind": "conversation",
        "park_path": "steps[0]",
        "park_seq": SEQ,
        "lane": "interactive",
        "budget_usd": None,
    }
    values.update(overrides)
    run = a_run(**values)
    world.seed(initiative, run)
    world.signals.writers.steps.add_many(
        [
            StepRun(
                id=new_id(),
                run_id=run.id,
                seq=1,
                path="steps[0]",
                label=step,
                kind="conversation",
                gate="human",
                status="checkpoint",
                with_resolved={"step": step},
            ),
            StepRun(
                id=new_id(),
                run_id=run.id,
                seq=2,
                path="steps[1]",
                label="after",
                kind="conversation",
                gate="human",
                status="planned",
                with_resolved={"step": "ux"},
            ),
        ]
    )
    return initiative, run


def forced() -> Signal:
    return Signal(kind="skip_step", stop=SEQ, payload={"forced": True})


def call(world: InitiativeWorld, initiative: Initiative, seq: int = SEQ) -> Initiative:
    with world.uow:
        return start_next(world.ports, initiative.id, seq)


def test_the_next_conversation_step_is_forced_with_the_stop_the_operator_saw() -> None:
    world = InitiativeWorld()
    initiative, run = parked(world)
    world.initiatives.calls.clear()

    result = call(world, initiative)

    assert result.id == initiative.id
    assert world.initiatives.calls == [("get_for_update", initiative.id)]
    assert ("signal", (run.id, forced())) in world.engine.calls
    assert world.uow.calls.count("commit") == 1


def test_a_stale_stop_is_refused_and_nothing_changes() -> None:
    world = InitiativeWorld()
    initiative, run = parked(world)

    with pytest.raises(Conflict, match="this signal names stop 9"):
        call(world, initiative, 9)

    assert world.engine.calls == []
    assert world.runs.runs[run.id] == run
    assert "rollback" in world.uow.calls


@pytest.mark.parametrize("step", ["tech", "gate", "unknown"])
def test_a_step_whose_next_is_not_a_conversation_is_refused(step: str) -> None:
    world = InitiativeWorld()
    initiative, _ = parked(world, step)

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NOT_FORCEABLE
    assert world.engine.calls == []
    assert "rollback" in world.uow.calls


def test_a_round_that_leaves_out_the_next_step_is_refused() -> None:
    world = InitiativeWorld()
    initiative, _ = parked(world, inputs={"round_steps": "product,tech"})

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NOT_FORCEABLE


def test_a_round_that_names_the_next_step_is_forced() -> None:
    world = InitiativeWorld()
    initiative, run = parked(world, inputs={"round_steps": "product,ux"})

    call(world, initiative)

    assert ("signal", (run.id, forced())) in world.engine.calls


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "running", "park_kind": None, "park_path": None},
        {"park_kind": "blocked"},
        {"park_path": "steps[7]"},
    ],
)
def test_no_open_conversation_is_refused(overrides: dict[str, Any]) -> None:
    world = InitiativeWorld()
    initiative, _ = parked(world, **overrides)

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NO_CONVERSATION
    assert world.engine.calls == []


def test_an_initiative_without_a_run_is_refused() -> None:
    world = InitiativeWorld()
    initiative = world.seed(world.initiative(sequence=sequence()))

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NO_CONVERSATION


def test_an_unknown_initiative_is_not_found() -> None:
    world = InitiativeWorld()

    with pytest.raises(NotFound):
        with world.uow:
            start_next(world.ports, new_id(), SEQ)


def test_the_latest_run_decides() -> None:
    world = InitiativeWorld()
    initiative, _ = parked(world)
    newer = a_run(
        project_id=world.project.id,
        repository_id=world.hub.id,
        initiative_id=initiative.id,
        initiative_round=2,
        initiative_position=0,
        status="running",
        minutes=5,
    )
    world.runs.add(newer)

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NO_CONVERSATION


def test_a_run_without_a_position_in_the_sequence_is_refused() -> None:
    world = InitiativeWorld()
    initiative, run = parked(world)
    world.runs.runs[run.id] = run.model_copy(update={"initiative_position": None})

    with pytest.raises(Conflict) as refusal:
        call(world, initiative)

    assert str(refusal.value) == NO_CONVERSATION
