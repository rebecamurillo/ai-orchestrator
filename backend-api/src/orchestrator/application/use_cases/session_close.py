"""The turn end of a conversation step session (AD-38 "Turn end"): the agent's attestation
that the owner said we are done, checked against the turn that wrote it.

`after_turn` runs once the turn's commit has committed and closed the attempt. It reads
`CLOSE_FILE`; only an attestation naming this very attempt, on a turn that ended `done`, with
no later message pending, sends `step_close` for the current stop. Every other attestation is
removed with one `close_discarded` record. Without an attestation nothing is sent, whatever
the step file says. The status is `signal_run`'s to write (AD-8); nothing here writes one.

`session_turn` calls this module and this module reads `session_turn`'s turn: both import
the module object, never a name from it.
"""

from __future__ import annotations

from uuid import UUID

import structlog

from orchestrator.application.rules import session
from orchestrator.application.rules.signals_conversation import CONVERSATION
from orchestrator.application.steps import agent_workdir
from orchestrator.application.steps.context import require_workspace
from orchestrator.application.use_cases import session_dispatch, session_turn
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.writers import Entry, record
from orchestrator.domain.errors import Conflict, Invalid
from orchestrator.domain.statuses import MachineEvent
from orchestrator.domain.values import Signal

log = structlog.get_logger(__name__)

CLOSE_DISCARDED: MachineEvent = "close_discarded"
DISCARDED_ATTEMPT = "close discarded: attempt {text}"
DEFERRED = "close deferred: later message"
DISCARDED_FAILED = "close discarded: turn failed"
NOT_WIRED = "step close not wired"
REFUSED = "step close refused"
PENDING = frozenset({"queued", "running"})
#: How much of a foreign attestation the discard record repeats.
ECHO_LIMIT = 64


def after_turn(ports: session_turn.TurnPorts, attempt_id: UUID) -> None:
    """Act on the attestation the finished turn left, if the Run is parked `conversation`."""
    turn = session_turn.read_turn(ports, attempt_id)
    if turn is None or turn.run.park_kind != CONVERSATION:
        return
    workspace = require_workspace(turn.ctx, str(agent_workdir.tree(turn.ctx)))
    # a link at the file is removed and never read through
    raw = (
        None
        if workspace.is_link(session.CLOSE_FILE)
        else workspace.read_lenient(session.CLOSE_FILE)
    )
    if raw is None:
        workspace.remove(session.CLOSE_FILE)
        return
    workspace.remove(session.CLOSE_FILE)
    discard = _verdict(turn, raw.strip())
    if discard is not None:
        _discard(ports, turn, discard)
        return
    _send(ports, turn)


def _verdict(turn: session_dispatch.Turn, text: str) -> str | None:
    """The reason the attestation closes nothing, or `None` when it closes the step."""
    attempt = turn.ctx.attempt
    if text != str(attempt.id):
        # the agent wrote it: bounded, and without the NUL a Postgres text column refuses
        return DISCARDED_ATTEMPT.format(text=text.replace("\x00", "")[:ECHO_LIMIT])
    if any(a.n > attempt.n and a.status in PENDING for a in turn.turns):
        return DEFERRED
    if attempt.status != "done":
        return DISCARDED_FAILED
    return None


def _discard(ports: session_turn.TurnPorts, turn: session_dispatch.Turn, text: str) -> None:
    writers = ports.writers
    with writers.uow:
        entry = Entry(
            event=CLOSE_DISCARDED,
            actor="machine",
            path=turn.ctx.row.path,
            text=text,
            attempt_n=turn.ctx.attempt.n,
        )
        record(writers, turn.run, entry)
        writers.uow.commit()


def _send(ports: session_turn.TurnPorts, turn: session_dispatch.Turn) -> None:
    run, attempt = turn.run, turn.ctx.attempt
    if ports.signal is None:
        log.warning(NOT_WIRED, run_id=str(run.id))
        return
    signal = Signal(kind="step_close", stop=run.park_seq, payload={"attempt_id": str(attempt.id)})
    try:
        signal_run(ports.signal, run.id, signal)
    except (Conflict, Invalid) as error:
        log.warning(REFUSED, reason=str(error), run_id=str(run.id))
