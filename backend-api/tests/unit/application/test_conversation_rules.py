"""The round and first-turn rules of a conversation step (epic 4 story 3, AC5; B8)."""

from __future__ import annotations

from typing import Any

from orchestrator.application.rules.conversation import (
    close_clause,
    first_turn,
    round_list,
    round_names_no_step,
    round_skips,
)
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id

STEPS = ("intake", "product", "ux", "tech")


def row(seq: int, step: str, kind: str = "conversation") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=new_id(),
        seq=seq,
        path=step,
        label=step,
        kind=kind,
        gate="human",
        status="planned",
        with_resolved={"step": step, "prompts": {"open": f"open {step}", "close": "close"}},
    )


def plan() -> list[StepRun]:
    return [row(1, "sync", "git.sync"), *(row(n, name) for n, name in enumerate(STEPS, start=2))]


def opening(inputs: dict[str, Any], name: str) -> str:
    rows = plan()
    target = next(entry for entry in rows if entry.path == name)
    return first_turn(target, rows, inputs)


def test_the_lowest_conversation_row_opens_with_the_first_turn() -> None:
    inputs = {"first_turn": "Build a habit tracker"}

    assert opening(inputs, "intake") == "Build a habit tracker"
    assert opening(inputs, "product") == "open product"


def test_a_round_opens_every_row_in_it_with_the_first_turn() -> None:
    inputs = {"round_steps": "ux,tech", "first_turn": "2 defects"}

    assert opening(inputs, "ux") == "2 defects"
    assert opening(inputs, "tech") == "2 defects"
    assert opening(inputs, "intake") == "open intake"


def test_a_blank_first_turn_leaves_each_row_its_own_open() -> None:
    for inputs in ({}, {"first_turn": ""}, {"first_turn": "  "}, {"first_turn": None}):
        assert opening(inputs, "intake") == "open intake"
        assert opening({**inputs, "round_steps": "ux"}, "ux") == "open ux"


def test_the_round_list_is_split_stripped_and_drops_empties() -> None:
    assert round_list({"round_steps": " ux , ,tech,"}) == ("ux", "tech")
    assert round_list({"round_steps": ""}) == ()
    assert round_list({"round_steps": None}) == ()
    assert round_list({}) == ()


def test_a_row_outside_a_non_empty_round_is_skipped() -> None:
    inputs = {"round_steps": "ux, tech"}

    assert [round_skips(entry, inputs) for entry in plan()[1:]] == [True, True, False, False]
    assert round_skips(plan()[1], {}) is False
    assert round_skips(plan()[1], {"round_steps": " , "}) is False


def test_a_round_naming_no_conversation_step_is_misconfigured() -> None:
    assert round_names_no_step(plan(), {"round_steps": "design"}) is True
    assert round_names_no_step(plan(), {"round_steps": "design, ux"}) is False
    assert round_names_no_step(plan(), {"round_steps": "sync"}) is True
    assert round_names_no_step(plan(), {}) is False
    assert round_names_no_step(plan(), {"round_steps": ","}) is False


def test_the_close_clause_names_the_attempt_wherever_the_token_stands() -> None:
    target = row(2, "intake")
    prompts = {"close": "write {attempt_id} to the file; again {attempt_id}"}
    target = target.model_copy(update={"with_resolved": {"prompts": prompts}})

    assert close_clause(target, "A2") == "write A2 to the file; again A2"


def test_a_row_without_a_close_prompt_has_no_close_clause() -> None:
    bare = row(2, "intake").model_copy(update={"with_resolved": {}})
    blank = row(2, "intake").model_copy(update={"with_resolved": {"prompts": {"close": None}}})

    assert close_clause(bare, "A2") == ""
    assert close_clause(blank, "A2") == ""
