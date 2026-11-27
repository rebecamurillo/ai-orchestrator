"""Which session turns a gate wrote (AD-37 "The transitions", epic 8 story 3).

A round opened by a failing gate gives each owner's Run the gate's `verdict_text` as its
`first_turn`; that first session turn is the gate's words, not the operator's. Read from what
the detail already loaded: no I/O.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.steps.gate_verdict import SPEC_GATE_ROLE
from orchestrator.application.use_cases.initiative_facts import conversation_step, session_turns
from orchestrator.application.use_cases.initiative_view_types import Loaded

FIRST_TURN = "first_turn"


def _verdicts(loaded: Loaded) -> dict[UUID, str]:
    """Run id to the text of the latest attempt of its `spec-gate` row, where one is stored."""
    found: dict[UUID, str] = {}
    for run in loaded.runs:
        for row in loaded.rows[run.id]:
            if row.role != SPEC_GATE_ROLE:
                continue
            attempts = [a for a in loaded.attempts[run.id] if a.step_run_id == row.id]
            latest = max(attempts, key=lambda a: a.n, default=None)
            if latest is not None and latest.verdict_text:
                found[run.id] = latest.verdict_text
    return found


def gate_turns(loaded: Loaded) -> dict[UUID, str]:
    """Attempt id to owner, for the first session turn of each owner's row in a gate round."""
    verdicts = _verdicts(loaded)
    owned: dict[UUID, str] = {}
    for run in loaded.runs:
        text = run.inputs.get(FIRST_TURN)
        if not text or not any(t == text for other, t in verdicts.items() if other != run.id):
            continue
        for row in loaded.rows[run.id]:
            if row.kind != CONVERSATION_KIND:
                continue
            turns = session_turns(row, loaded.attempts[run.id])
            if turns:
                owned[turns[0].id] = conversation_step(row)
    return owned
