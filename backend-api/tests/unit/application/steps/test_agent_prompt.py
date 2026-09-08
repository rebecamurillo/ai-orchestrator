"""`compose_prompt`: the sentence FR-14 pins, and the two things that may follow it.

The prompt is the whole interface between a Template and a coding agent, so it is asserted
as a whole string rather than by substring: a missing space or a reordered clause is a
different instruction, and nothing else in the system would notice.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import compose_prompt
from tests.unit.application.steps.agent_fixtures import (
    a_gate_record,
    an_agent_row,
    an_attempt,
    resolved,
)

FIRST = (
    "Run the skill bmad-build-auto in folder+id dispatch mode: "
    "spec folder specs/notifications, story id 4-1."
)


def prompt(with_resolved: dict[str, Any], **over: Any) -> str:
    return compose_prompt(
        with_resolved,
        over.get("resume_signal"),
        over.get("previous_attempt"),
    )


def test_a_plain_dispatch_is_the_sentence_and_what_the_template_bound() -> None:
    assert prompt(resolved()) == f"{FIRST} Read X."


def test_a_row_with_no_prompt_extra_is_the_sentence_alone_with_no_trailing_space() -> None:
    """A trailing space would be a difference no reader could see and every diff would."""
    assert prompt(resolved(prompt_extra="")) == FIRST
    assert prompt(resolved(prompt_extra=None)) == FIRST


def test_a_row_that_never_carried_the_key_is_the_sentence_alone() -> None:
    without = resolved()
    del without["prompt_extra"]

    assert prompt(without) == FIRST


def test_a_spec_checkpoint_asks_the_agent_to_halt_after_planning() -> None:
    assert prompt(resolved(spec_checkpoint=True)) == f"{FIRST} Read X. Halt after planning."


def test_a_resumed_spec_checkpoint_does_not_halt_again() -> None:
    """`continue` on the checkpoint means the plan was approved; halting again would park
    the Run on the stop it has just left."""
    row = an_agent_row()

    assert (
        prompt(resolved(spec_checkpoint=True), resume_signal=a_gate_record(row, "continue"))
        == f"{FIRST} Read X."
    )


def test_an_answer_signal_is_quoted_to_the_agent_with_its_condition() -> None:
    row = an_agent_row()
    record = a_gate_record(row, "answer", {"condition": "C", "answer": "A"})

    assert prompt(resolved(), resume_signal=record) == (
        f'{FIRST} Read X. Answer from the operator to the blocking condition "C": A'
    )


def test_an_answer_with_no_payload_still_composes_a_sentence() -> None:
    """`signal_run` stores whatever the payload held; a missing key is empty, not a crash."""
    row = an_agent_row()

    assert prompt(resolved(), resume_signal=a_gate_record(row, "answer")) == (
        f'{FIRST} Read X. Answer from the operator to the blocking condition "": '
    )


def test_a_row_missing_the_skill_the_folder_or_the_id_still_renders_one_sentence() -> None:
    """The planner always fills all three; the empty rendering is a readable dispatch and
    not a `KeyError` inside a durable step."""
    empty = resolved(skill="", spec_folder="", story_id="", prompt_extra="")

    assert prompt(empty) == "Run the skill  in folder+id dispatch mode: spec folder , story id ."


def test_the_previous_attempt_is_accepted_and_changes_nothing_yet() -> None:
    """5.5 composes the retry prompt from it; taking it now keeps that story out of the
    call sites."""
    row = an_agent_row()

    assert prompt(resolved(), previous_attempt=an_attempt(row, 1)) == f"{FIRST} Read X."
