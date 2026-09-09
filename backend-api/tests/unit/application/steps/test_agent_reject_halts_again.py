"""`compose_prompt`'s halt decision at a spec checkpoint (story 6-2, SPEC CAP-2, FR-19):
Reject halts again, and nothing else that resumes an `agent` row does.

Strictly-exceeding coverage for the correction to `test_agent_answer_dispatch.py::
test_a_spec_checkpoint_answer_quotes_spec_rejected_and_halts_again` (renamed from
`..._and_does_not_halt_again` — story 6-1 guessed wrong about a behaviour this story's own
brief governs; the operator authorised the fix). Where that test proves the full executor
dispatch carries the halt, this module pins `compose_prompt` itself, whole-string, the same
way `test_agent_prompt.py` does — and adds the one contrast that test file does not have: a
`blocked` Answer (6.1's own case, `spec_checkpoint` false) still carries no halt suffix, so
the two paths can never silently converge again.
"""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps.agent import compose_prompt
from tests.unit.application.steps.agent_fixtures import (
    a_gate_record,
    an_agent_row,
    resolved,
)

FIRST = (
    "Run the skill bmad-build-auto in folder+id dispatch mode: "
    "spec folder specs/notifications, story id 4-1."
)

CONDITION = "spec rejected"
REASON = "split the endpoint in two"


def prompt(with_resolved: dict[str, Any], resume_signal: Any) -> str:
    return compose_prompt(with_resolved, resume_signal, None)


def test_a_reject_at_a_spec_checkpoint_quotes_spec_rejected_and_halts_again() -> None:
    """The brief's own acceptance criterion, verbatim: the Answer clause, then the halt."""
    row = an_agent_row()
    record = a_gate_record(row, "answer", {"condition": CONDITION, "answer": REASON})

    assert prompt(resolved(spec_checkpoint=True), record) == (
        f'{FIRST} Read X. Answer from the operator to the blocking condition "{CONDITION}": '
        f"{REASON} Halt after planning."
    )


def test_a_blocked_answer_still_carries_no_halt_suffix() -> None:
    """The contrast case: 6.1's own scenario, `spec_checkpoint` false, is untouched by 6.2's
    new rule — an Answer that resumes a `blocked` row never halts, checkpoint or not."""
    row = an_agent_row()
    record = a_gate_record(row, "answer", {"condition": "intent gap", "answer": REASON})

    result = prompt(resolved(spec_checkpoint=False), record)

    assert result == (
        f'{FIRST} Read X. Answer from the operator to the blocking condition "intent gap": {REASON}'
    )
    assert "Halt after planning." not in result


def test_a_continue_at_a_spec_checkpoint_still_never_halts_again() -> None:
    """The other half of the contrast: `continue` means the plan was approved, so it stays
    exactly as `test_agent_prompt.py::test_a_resumed_spec_checkpoint_does_not_halt_again`
    already pins — restated here so this module's own `assert` covers both branches of
    `agent_answer.halts_after_planning` that touch a real resume, side by side."""
    row = an_agent_row()
    record = a_gate_record(row, "continue")

    result = prompt(resolved(spec_checkpoint=True), record)

    assert result == f"{FIRST} Read X."
    assert "Halt after planning." not in result
