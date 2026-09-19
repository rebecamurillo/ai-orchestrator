"""story 4-9 (2026-09-17): intent dispatch form in compose_prompt —
DISPATCH_INTENT and INTENT_KEY are architectural anchors"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import compose_prompt

# DISPATCH_INTENT, HALT, INTENT_KEY imports are the hard TDD gate
from orchestrator.application.steps.agent_prompt import DISPATCH_INTENT, HALT, INTENT_KEY
from tests.unit.application.steps.agent_fixtures import a_gate_record, an_agent_row


def resolved(**over: Any) -> dict[str, Any]:
    """Minimal with_resolved for intent dispatch tests — no prompt_extra, spec_checkpoint False."""
    base: dict[str, Any] = {
        "skill": "bmad-build-auto",
        "spec_checkpoint": False,
    }
    base.update(over)
    return base


def prompt(with_resolved: dict[str, Any], **over: Any) -> str:
    return compose_prompt(
        with_resolved,
        over.get("resume_signal"),
        over.get("previous_attempt"),
    )


def test_intent_dispatch_uses_dispatch_intent_prefix_and_intent_text() -> None:
    r = resolved(**{INTENT_KEY: "gh-47: Fix auth"}, skill="bmad-build-auto")
    expected = DISPATCH_INTENT.format(skill="bmad-build-auto") + "gh-47: Fix auth"
    assert prompt(r) == expected


def test_intent_with_curly_braces_does_not_raise() -> None:
    intent = "Fix {auth} bug"
    r = resolved(**{INTENT_KEY: intent})
    p = prompt(r)
    assert "Fix {auth} bug" in p


def test_intent_dispatch_adds_halt_when_spec_checkpoint() -> None:
    r = resolved(spec_checkpoint=True, **{INTENT_KEY: "gh-47: Fix auth"})
    p = prompt(r)
    assert p.endswith(HALT)


def test_intent_dispatch_no_halt_on_continue_resume() -> None:
    row = an_agent_row()
    r = resolved(spec_checkpoint=True, **{INTENT_KEY: "gh-47: Fix auth"})
    p = prompt(r, resume_signal=a_gate_record(row, "continue"))
    assert HALT not in p


def test_no_intent_falls_back_to_dispatch_sentence() -> None:
    """Without an intent key the folder+id DISPATCH form is used (regression guard)."""
    r = resolved()  # no intent key
    p = prompt(r)
    assert p.startswith("Run the skill")
    assert "folder+id dispatch mode" in p


def test_dispatch_intent_constant_value() -> None:
    """Pins the exact prefix the harness sees — a silent change here would alter all tasks."""
    assert DISPATCH_INTENT == "Run the skill {skill} with the following intent:\n\n"
