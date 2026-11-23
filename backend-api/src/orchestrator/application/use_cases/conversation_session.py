"""A conversation step's session, opened with the park (AD-23 amended, "Opening").

Reused by epic 8 story 4 for the epic-scoped session.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID

from orchestrator.application.rules import conversation, session
from orchestrator.application.use_cases.writers import Entry, WriterPorts, record, set_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id

STARTED_TEXT = "step session started"


def _text(value: Any) -> str | None:
    return str(value) if value else None


def open_step_session(
    ports: WriterPorts, run: Run, rows: Sequence[StepRun], row: StepRun
) -> UUID | None:
    """Record the session, flag the Run, and queue the row's first turn the first time only.

    Returns the new attempt's id, or `None` when the row already held a session turn.
    """
    harness = _text(run.inputs.get(session.HARNESS_KEY))
    model = _text(run.inputs.get(session.MODEL_KEY))
    record(
        ports,
        run,
        Entry(
            event=session.SESSION_START,
            actor="machine",
            path=row.path,
            text=STARTED_TEXT,
            payload={
                session.SCOPE_KEY: session.STEP_SCOPE,
                session.HARNESS_KEY: run.inputs.get(session.HARNESS_KEY),
                session.MODEL_KEY: run.inputs.get(session.MODEL_KEY),
            },
        ),
    )
    set_run(ports, run, senior_session=True)
    attempts = ports.attempts.list_for_row(row.id)
    if any(attempt.role == session.SESSION_ROLE for attempt in attempts):
        return None
    turn = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=row.id,
        n=max((attempt.n for attempt in attempts), default=0) + 1,
        status="queued",
        role=session.SESSION_ROLE,
        started_at=ports.clock.now(),
        message=conversation.first_turn(row, rows, run.inputs),
        harness=harness,
        model=model,
    )
    ports.attempts.add(turn)
    return turn.id
