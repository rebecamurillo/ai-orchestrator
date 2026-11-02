"""The start-up sweep of senior session turns (AD-6, AD-23): a turn whose attempt was
committed but whose enqueue a crash lost is enqueued again, or closed when its session has
ended since. A turn the engine already holds is the engine's to recover; enqueueing it again
under its attempt id finds the workflow already there.
"""

from __future__ import annotations

from orchestrator.application.rules import session
from orchestrator.application.use_cases.session_turn import SESSION_CLOSED
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.engine import WorkflowEngine


def sweep_session_turns(ports: WriterPorts, engine: WorkflowEngine) -> None:
    """Enqueue every queued turn of an open session; close the rest `session closed`."""
    for attempt in ports.attempts.list_queued_sessions():
        run = ports.runs.get(attempt.run_id)
        if run is not None and session.session_open(run):
            engine.enqueue_session_turn(run.id, attempt.id)
            continue
        with ports.uow:
            closed = attempt.model_copy(
                update={
                    "status": "error",
                    "output_ref": SESSION_CLOSED,
                    "ended_at": ports.clock.now(),
                }
            )
            ports.attempts.mark_finished(closed)
            ports.uow.commit()
