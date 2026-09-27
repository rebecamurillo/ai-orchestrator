"""story 4-9 (2026-09-17): the intent dispatch form in `compose_prompt`.

Revised 2026-09-27 (Operator decision: prompt prose lives in the Template): the
`DISPATCH_INTENT` constant is gone — the intent form is a `dispatch` clause naming
`{intent}`, filled at runtime with the Operator's pasted text, inserted literally so
braces inside it stay inert.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import compose_prompt
from orchestrator.application.steps.agent_prompt import INTENT_KEY
from tests.unit.application.steps.agent_fixtures import a_gate_record, an_agent_row

#: The clauses shipped `task@1` declares, as the planner leaves them on the row.
INTENT_DISPATCH = "Run the skill {skill} with the following intent:\n\n{intent}"
HALT = "Halt after planning."
PROMPTS = {"dispatch": INTENT_DISPATCH, "halt": HALT}


def resolved(**over: Any) -> dict[str, Any]:
    """Minimal with_resolved for intent dispatch tests — no prompt_extra, no checkpoint."""
    base: dict[str, Any] = {
        "skill": "bmad-build-auto",
        "spec_checkpoint": False,
        "prompts": dict(PROMPTS),
    }
    base.update(over)
    return base


def prompt(with_resolved: dict[str, Any], **over: Any) -> str:
    return compose_prompt(
        with_resolved,
        over.get("resume_signal"),
        over.get("previous_attempt"),
    )


def test_intent_dispatch_fills_the_clause_with_skill_and_intent() -> None:
    r = resolved(**{INTENT_KEY: "gh-47: Fix auth"})

    expected = "Run the skill bmad-build-auto with the following intent:\n\ngh-47: Fix auth"
    assert prompt(r) == expected


def test_intent_with_curly_braces_does_not_raise() -> None:
    """The fill is one literal-insertion pass: braces in the pasted text stay inert."""
    r = resolved(**{INTENT_KEY: "Fix {auth} bug"})

    assert "Fix {auth} bug" in prompt(r)


def test_an_intent_naming_a_placeholder_is_not_rescanned() -> None:
    """A pasted `{skill}` arrives as those six characters, never as the skill's name."""
    r = resolved(**{INTENT_KEY: "mention {skill} verbatim"})

    assert prompt(r).endswith("mention {skill} verbatim")


def test_intent_dispatch_adds_the_halt_clause_when_spec_checkpoint() -> None:
    r = resolved(spec_checkpoint=True, **{INTENT_KEY: "gh-47: Fix auth"})

    assert prompt(r).endswith(HALT)


def test_intent_dispatch_no_halt_on_continue_resume() -> None:
    row = an_agent_row()
    r = resolved(spec_checkpoint=True, **{INTENT_KEY: "gh-47: Fix auth"})

    assert HALT not in prompt(r, resume_signal=a_gate_record(row, "continue"))


def test_a_clause_without_the_intent_token_sends_the_clause_alone() -> None:
    """The clause decides what the intent contributes: a template whose dispatch names no
    `{intent}` sends its own sentence and the pasted text goes nowhere."""
    r = resolved(prompts={"dispatch": "Run the skill {skill}."}, **{INTENT_KEY: "gh-47: Fix auth"})

    assert prompt(r) == "Run the skill bmad-build-auto."
