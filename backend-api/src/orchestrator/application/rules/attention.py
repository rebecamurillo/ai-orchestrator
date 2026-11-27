"""What a parked Run asks of the Operator, read from facts already stored (AD-36 "Attention").

Pure. `attention` is `None` unless the Run waits for her; a `conversation` stop is told apart
by the `session` attempts of the parked row.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from orchestrator.application.rules import conversation, session
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

Attention = Literal["queued", "answering", "blocked", "your_turn"]

#: The prefix of every `step not closed` park reason (`steps/conversation.py`).
STEP_NOT_CLOSED = "step not closed"
ERROR = "error"
FIRST_TURNS = 2
_LIVE = ("queued", "running")


def attention(
    run: Run,
    rows: Sequence[StepRun],
    attempts: Sequence[Attempt],
    *,
    step_word: str | None,
) -> Attention | None:
    if run.status != "needs_you":
        return None
    if run.park_kind != CONVERSATION_KIND:
        return "blocked"
    row = next((r for r in rows if r.path == run.park_path), None)
    turns = _turns(row, attempts)
    busy = _busy(turns)
    if busy is not None:
        return busy
    if _failed_turn(turns) or _declared_blocked(row, step_word) or _not_closed(run, turns):
        return "blocked"
    return "your_turn"


def _turns(row: StepRun | None, attempts: Sequence[Attempt]) -> tuple[Attempt, ...]:
    if row is None:
        return ()
    return tuple(a for a in attempts if a.step_run_id == row.id and a.role == session.SESSION_ROLE)


def _busy(turns: Sequence[Attempt]) -> Attention | None:
    if not any(t.status == "running" for t in turns):
        return None
    return "queued" if any(t.status == "queued" for t in turns) else "answering"


def _failed_turn(turns: Sequence[Attempt]) -> bool:
    ended = [t for t in turns if t.status not in _LIVE]
    return bool(ended) and max(ended, key=lambda t: t.n).status == ERROR


def _declared_blocked(row: StepRun | None, step_word: str | None) -> bool:
    if row is None or step_word is None:
        return False
    expect = row.with_resolved.get("expect")
    declared = expect if isinstance(expect, Mapping) else {}
    return step_word in {str(w) for w in declared.get("blocked") or ()}


def _not_closed(run: Run, turns: Sequence[Attempt]) -> bool:
    if (run.park_reason or "").startswith(STEP_NOT_CLOSED):
        return True
    return bool(conversation.round_list(run.inputs)) and len(turns) < FIRST_TURNS
