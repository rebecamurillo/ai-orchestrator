"""The start-up sweep of senior session turns (AD-6, AD-23).

A `queued` turn whose enqueue a crash lost is enqueued again, or closed when its session has
ended since; enqueueing a turn the engine already holds finds the workflow already there.
A turn past `queued` that the engine does not hold had its workflow end in error, and the
engine recovers no such workflow: left open, it would refuse every message and the close
for the rest of the session. It is interrupted if it was running, then committed, closed and
billed here, through the two steps the workflow would have run.

`held` is the caller's read of the engine's session queue, taken before the turns are
listed, so a workflow that finishes in between is seen closed rather than recovered twice.
"""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

import structlog

from orchestrator.application.rules import session
from orchestrator.application.use_cases.session_dispatch import SESSION_CLOSED
from orchestrator.application.use_cases.session_turn import TurnPorts, commit_turn, run_turn
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.engine import WorkflowEngine

log = structlog.get_logger(__name__)

RECOVERY_FAILED = "session turn recovery failed"


def sweep_session_turns(
    ports: TurnPorts, engine: WorkflowEngine, held: Collection[UUID] = ()
) -> None:
    """Enqueue or close every queued turn; recover every other open turn not `held`."""
    for attempt in ports.writers.attempts.list_open_sessions():
        if attempt.status == "queued":
            _requeue(ports, engine, attempt)
        elif attempt.id not in held:
            _recover(ports, attempt)


def _requeue(ports: TurnPorts, engine: WorkflowEngine, attempt: Attempt) -> None:
    writers = ports.writers
    run = writers.runs.get(attempt.run_id)
    if run is not None and session.session_open(run):
        engine.enqueue_session_turn(run.id, attempt.id)
        return
    with writers.uow:
        closed = attempt.model_copy(
            update={
                "status": "error",
                "output_ref": SESSION_CLOSED,
                "ended_at": writers.clock.now(),
            }
        )
        writers.attempts.mark_finished(closed)
        writers.uow.commit()


def _recover(ports: TurnPorts, attempt: Attempt) -> None:
    """One failure is logged with its turn, so the turns after it are still recovered."""
    try:
        run_turn(ports, attempt.id)
        commit_turn(ports, attempt.id)
    except Exception:
        log.exception(RECOVERY_FAILED, run_id=str(attempt.run_id), attempt=attempt.n)
