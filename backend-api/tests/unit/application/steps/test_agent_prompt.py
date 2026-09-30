"""`compose_prompt`: the row's own clauses, filled and joined (FR-14).

Revised 2026-09-27 (Operator decision: prompt prose lives in the Template): every sentence
below comes from the fixture's `prompts` clauses — the same texts the shipped templates
declare — and what this module pins is the composition: which clause fires when, what fills
its placeholders, and that the orchestrator adds no words of its own. The prompt is the
whole interface between a Template and a coding agent, so it is asserted as a whole string
rather than by substring: a missing space or a reordered clause is a different instruction,
and nothing else in the system would notice.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import compose_prompt
from orchestrator.application.steps.agent_prompt import redispatch_clause
from orchestrator.application.steps.context import VerifyFailure
from orchestrator.application.story_file import NO_EXIT_CODE
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


# ── the orchestrator adds no words of its own (Operator decision, 2026-09-27) ───────────


def test_an_undeclared_answer_clause_appends_the_operators_words_alone() -> None:
    """Their words are not orchestrator prose; no clause means no quoting around them."""
    row = an_agent_row()
    record = a_gate_record(row, "answer", {"condition": "C", "answer": "use the queue"})

    assert prompt(resolved(prompts={}), resume_signal=record) == "Read X. use the queue"


def test_a_row_with_no_clauses_at_all_composes_from_empty_parts_without_raising() -> None:
    """A stored version predating the clauses is a validation concern, never a `KeyError`
    inside a durable step."""
    bare = resolved(prompts={}, prompt_extra="")

    assert prompt(bare) == ""


def test_a_clause_naming_an_unknown_token_keeps_it_as_literal_prose() -> None:
    unknown = resolved(prompts={"dispatch": "Go to {storyid} now."}, prompt_extra="")

    assert prompt(unknown) == "Go to {storyid} now."


def test_a_filled_value_is_never_rescanned_for_tokens_of_its_own() -> None:
    """One literal-insertion pass: a spec folder spelled `{answer}` arrives verbatim."""
    tricky = resolved(spec_folder="{answer}", prompt_extra="")

    assert "spec folder {answer}," in prompt(tricky)


# ── the `redispatch` clause (a fifth clause, FR-10, story "a redispatch prompt clause") ──


def test_redispatch_clause_fills_the_command_the_code_and_the_tail() -> None:
    with_resolved = resolved(
        prompts={"redispatch": "Verify failed: {command} (exit {code}).\n{tail}"}
    )
    failure = VerifyFailure(
        command="make test", exit_code=1, log_tail=("FAILED tests/a.py", "1 failed")
    )

    assert redispatch_clause(with_resolved, failure) == (
        "Verify failed: make test (exit 1).\nFAILED tests/a.py\n1 failed"
    )


def test_redispatch_clause_states_no_exit_code_was_recorded() -> None:
    with_resolved = resolved(prompts={"redispatch": "Exit code: {code}."})
    failure = VerifyFailure(command="make test", exit_code=None, log_tail=())

    assert redispatch_clause(with_resolved, failure) == f"Exit code: {NO_EXIT_CODE}."


def test_redispatch_clause_leaves_a_tail_containing_tokens_of_its_own_as_literal_prose() -> None:
    with_resolved = resolved(prompts={"redispatch": "{tail}"})
    failure = VerifyFailure(
        command="make test", exit_code=1, log_tail=("saw {command} and {skill} in the log",)
    )

    assert redispatch_clause(with_resolved, failure) == "saw {command} and {skill} in the log"


def test_an_undeclared_redispatch_clause_is_empty() -> None:
    with_resolved = resolved(prompts={})
    failure = VerifyFailure(command="make test", exit_code=1, log_tail=())

    assert redispatch_clause(with_resolved, failure) == ""


def test_a_dispatch_clause_never_starts_filling_the_redispatch_tokens() -> None:
    """`{tail}` written in a `dispatch` clause is not one of `_base`'s tokens: it stays
    literal prose, the same way an unknown token does."""
    with_resolved = resolved(
        prompts={"dispatch": "Mind the {tail} left by the last run.", "rendered": ""},
        prompt_extra="",
    )

    assert prompt(with_resolved) == "Mind the {tail} left by the last run."
