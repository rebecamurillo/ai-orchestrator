"""Restart a failed turn (AD-23, FR-13): one `queued` `session` attempt carrying the failed
turn's message, enqueued like a posted one. Its dispatch resumes the harness session the
earlier turns recorded.

Only `attempt` rows are written; no Run or Step status (AD-8).
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from orchestrator.application.rules import budget, session
from orchestrator.application.rules.signals import row_at
from orchestrator.application.use_cases.session_checks import NO_BUDGET
from orchestrator.application.use_cases.session_turn import (
    NO_SESSION,
    MessagePorts,
    close_turn,
)
from orchestrator.application.use_cases.session_view import SessionTurn, turn_of
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.application.use_cases.writers import require_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id

NOT_FAILED = "the last turn did not fail"


def retry_turn(ports: MessagePorts, run_id: UUID) -> SessionTurn:
    """Queue the last failed turn again on the parked row, then enqueue it."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id, lock=True)
        row = row_at(writers.steps.list_for_run(run_id), run.park_path)
        if row is None or not session.session_open(run):
            raise Conflict(NO_SESSION)
        attempts = writers.attempts.list_for_row(row.id)
        records = writers.records.list_for_run(run_id)
        turns = session.session_attempts(attempts, records)
        failed = _refuse(run, turns)
        started = session.last_start_payload(records)
        attempt = Attempt(
            id=new_id(),
            run_id=run_id,
            step_run_id=row.id,
            n=max(a.n for a in attempts) + 1,
            status="queued",
            role=session.SESSION_ROLE,
            started_at=writers.clock.now(),
            message=failed.message,
            harness=_text(started.get(session.HARNESS_KEY)),
            model=_text(started.get(session.MODEL_KEY)),
        )
        writers.attempts.add(attempt)
        writers.uow.commit()
    try:
        ports.engine.enqueue_session_turn(run_id, attempt.id)
    except Exception as error:
        close_turn(writers, attempt, str(error))
        raise
    return turn_of(attempt, len(turns) + 1)


def _refuse(run: Run, turns: Sequence[Attempt]) -> Attempt:
    """Every refusal, before the write; the failed turn it returns is the one to repeat."""
    if session.turn_open(turns):
        raise Conflict(TURN_RUNNING)
    last = max(turns, key=lambda turn: turn.n, default=None)
    if last is None or last.status != "error":
        raise Conflict(NOT_FAILED)
    if run.budget_usd is not None and run.budget_usd - budget.figure(run) <= 0:
        raise Conflict(NO_BUDGET)
    return last


def _text(value: object) -> str | None:
    return str(value) if value else None
