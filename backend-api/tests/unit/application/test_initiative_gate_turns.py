"""The first turn of each owner in a gate round reads `author: gate` (epic 8 story 3, AC15)."""

from __future__ import annotations

from typing import Any

from orchestrator.application.use_cases.initiative_gate_turns import gate_turns
from orchestrator.application.use_cases.initiative_view_types import Loaded
from orchestrator.application.use_cases.initiative_views import initiative_detail
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run
from tests.unit.application.initiative_read_world import ReadWorld, sequence

VERDICT = "- the epics lack an owner\n- SPEC.md has no constraints\nplain line"


def seed(*, first_turn: str | None, verdict: str = VERDICT) -> tuple[ReadWorld, Initiative]:
    world = ReadWorld()
    initiative = world.initiative(sequence=sequence(), round=2)
    first = world.run(initiative, status="done", inputs={"first_turn": "hello"})
    world.row(first, 1, status="done")
    gate = world.row(first, 2, kind="shell", role="spec-gate", with_resolved={})
    world.turn(gate, 1, role="agent", verdict_word="fail", verdict_text=verdict)
    inputs: dict[str, Any] = {} if first_turn is None else {"first_turn": first_turn}
    second = world.run(initiative, minutes=30, initiative_round=2, status="running", inputs=inputs)
    row = world.row(second, 1, status="running")
    world.turn(row, 1, message="- first defect\n- second defect\nnote")
    world.turn(row, 2, message="operator typed")
    return world, initiative


def turns_of(world: ReadWorld, initiative: Initiative) -> list[Any]:
    detail = initiative_detail(world.ports, initiative.id)
    return [t for s in detail.workflows[0].steps for t in s.turns]


def test_the_first_turn_of_an_owner_in_a_gate_round_is_the_gates() -> None:
    world, initiative = seed(first_turn=VERDICT)

    turns = turns_of(world, initiative)

    gate_turns = [t for t in turns if t.author == "gate"]
    assert [(t.n, t.defects, t.owner) for t in gate_turns] == [(1, 2, "intake")]
    assert all(
        (t.author, t.defects, t.owner) == ("operator", None, None) for t in turns if t.n != 1
    )


def test_a_round_without_a_matching_first_turn_keeps_operator_turns() -> None:
    world, initiative = seed(first_turn="something else")

    assert all(t.author == "operator" for t in turns_of(world, initiative))


def test_a_round_without_a_first_turn_input_keeps_operator_turns() -> None:
    world, initiative = seed(first_turn=None)

    assert all(t.author == "operator" for t in turns_of(world, initiative))


def test_an_empty_verdict_text_is_never_a_match() -> None:
    world, initiative = seed(first_turn="", verdict="")

    assert all(t.author == "operator" for t in turns_of(world, initiative))


def test_a_run_whose_first_turn_is_its_own_gates_text_is_not_matched_to_itself() -> None:
    world, initiative = seed(first_turn="hello")
    spec: Run = next(r for r in world.runs.runs.values() if r.inputs.get("first_turn") == "hello")
    assert spec.status == "done"

    assert all(t.author == "operator" for t in turns_of(world, initiative))


def test_an_initiative_with_no_runs_has_no_gate_turns() -> None:
    _, initiative = seed(first_turn=VERDICT)

    assert gate_turns(Loaded(initiative, runs=[], rows={}, attempts={}, facts={})) == {}


def test_rows_that_are_not_conversations_or_have_no_turns_are_skipped() -> None:
    world, initiative = seed(first_turn=VERDICT)
    second = next(r for r in world.runs.runs.values() if r.inputs.get("first_turn") == VERDICT)
    world.row(second, 2, kind="shell", with_resolved={})
    world.row(second, 3, with_resolved={"step": "product"})

    turns = turns_of(world, initiative)

    assert [(t.n, t.author, t.owner) for t in turns if t.author == "gate"] == [
        (1, "gate", "intake")
    ]
