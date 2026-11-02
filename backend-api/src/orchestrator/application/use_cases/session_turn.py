"""A turn of the Operator's senior session (AD-8, AD-21, AD-23): the message that queues it,
and the two engine steps of its own workflow, outside the walk.

`post_message` is the request's half. Under the Run's row lock it refuses or adds one
`queued` `session` attempt, commits, and only then asks the engine for the turn, so the
workflow never reads an attempt that is not there. A failed enqueue closes that attempt.

`run_turn` is the `session_turn` step and `commit_turn` the `session_commit` step. The
workflow calls the second on every path, so a turn is always closed, billed and, unless the
Run ended, committed. Both read the turn afresh, so a step the engine re-executes after a
crash finds what the last one left: a `running` turn is interrupted rather than dispatched
twice, and a commit over a clean tree commits nothing.

Every write is an `attempt` row, its own `status` included; nothing here writes a Run or
Step status (AD-8, as amended for AD-23).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import structlog

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import row_at
from orchestrator.application.steps import agent_workdir
from orchestrator.application.steps.agent_consult_review import read_decision
from orchestrator.application.steps.context import (
    RunEnvironment,
    StepPorts,
    committed,
    require_workspace,
)
from orchestrator.application.use_cases import session_dispatch
from orchestrator.application.use_cases.session_checks import NO_BUDGET
from orchestrator.application.use_cases.session_dispatch import Turn
from orchestrator.application.use_cases.session_view import SessionTurn, turn_of
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.application.use_cases.spend import record_attempt_spend
from orchestrator.application.use_cases.start_attempt import INTERRUPTED
from orchestrator.application.use_cases.walk_context import context
from orchestrator.application.use_cases.writers import WriterPorts, require_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.statuses import TERMINAL_RUN

log = structlog.get_logger(__name__)

NO_SESSION = "no senior session open"
EMPTY_MESSAGE = "message text is empty"
SESSION_CLOSED = "session closed"
RAISED = "{name}: {message}"
TURN_FAILED = "session turn failed"
COMMIT_FAILED = "session commit failed"
#: The two statuses a turn holds before it has run; one still held at the commit was cut short.
UNRUN = frozenset({"queued", "running"})

#: One Run's environment, read for the turn as the walker reads it for a row.
ReadEnvironment = Callable[[UUID], RunEnvironment | None]


@dataclass(frozen=True)
class MessagePorts:
    writers: WriterPorts
    engine: WorkflowEngine


@dataclass(frozen=True)
class TurnPorts:
    """A step's writers, the executors' ports, and the Run's environment reader."""

    writers: WriterPorts
    step: StepPorts
    read_environment: ReadEnvironment | None = None


def post_message(ports: MessagePorts, run_id: UUID, text: str) -> SessionTurn:
    """Queue one turn on the parked row, then enqueue it (AD-23)."""
    writers = ports.writers
    with writers.uow:
        run = require_run(writers, run_id, lock=True)
        row = row_at(writers.steps.list_for_run(run_id), run.park_path)
        if row is None or not session.session_open(run):
            raise Conflict(NO_SESSION)
        if not text.strip():
            raise Invalid(EMPTY_MESSAGE)
        attempts = writers.attempts.list_for_row(row.id)
        records = writers.records.list_for_run(run_id)
        turns = session.session_attempts(attempts, records)
        if session.turn_open(turns):
            raise Conflict(TURN_RUNNING)
        if run.budget_usd is not None and run.budget_usd - run.spend_usd <= 0:
            raise Conflict(NO_BUDGET)
        started = session.last_start_payload(records)
        attempt = Attempt(
            id=new_id(),
            run_id=run_id,
            step_run_id=row.id,
            n=max((a.n for a in attempts), default=0) + 1,
            status="queued",
            role=session.SESSION_ROLE,
            started_at=writers.clock.now(),
            message=text,
            harness=_text(started.get(session.HARNESS_KEY)),
            model=_text(started.get(session.MODEL_KEY)),
        )
        writers.attempts.add(attempt)
        writers.uow.commit()
    try:
        ports.engine.enqueue_session_turn(run_id, attempt.id)
    except Exception as error:
        _close(writers, attempt, str(error))
        raise
    return turn_of(attempt, len(turns) + 1)


def read_turn(ports: TurnPorts, attempt_id: UUID) -> Turn | None:
    """The turn as it is stored now, with the parked row's context around it."""
    writers = ports.writers
    with writers.uow:
        attempt = writers.attempts.get(attempt_id)
        if attempt is None:
            return None
        run = require_run(writers, attempt.run_id)
        rows = writers.steps.list_for_run(run.id)
        row = next((entry for entry in rows if entry.id == attempt.step_run_id), None)
        if row is None:
            raise NotFound(f"no step for attempt {attempt_id}")
        env = ports.read_environment(run.id) if ports.read_environment is not None else None
        step = replace(ports.step, run_env=env) if env is not None else ports.step
        ctx = replace(context(writers, step, run, row.seq, None), attempt=attempt)
        records = writers.records.list_for_run(run.id)
        turns = session.session_attempts(writers.attempts.list_for_row(row.id), records)
        scope = str(session.last_start_payload(records).get(session.SCOPE_KEY) or "")
    return Turn(ctx=ctx, run=run, turns=turns, scope=scope)


def run_turn(ports: TurnPorts, attempt_id: UUID) -> None:
    """`session_turn`: dispatch a queued turn; interrupt one a crash left running."""
    turn = read_turn(ports, attempt_id)
    if turn is None:
        return
    ctx = turn.ctx
    if ctx.attempt.status == "running":
        session_dispatch.interrupt(ctx, INTERRUPTED)
        return
    if ctx.attempt.status != "queued":
        return
    if not session.session_open(turn.run):
        session_dispatch.record(ctx, status="error", output_ref=SESSION_CLOSED)
        return
    try:
        session_dispatch.dispatch(turn)
    except Exception as error:
        log.exception(TURN_FAILED, run_id=str(turn.run.id), attempt=ctx.attempt.n)
        session_dispatch.record(ctx, status="error", output_ref=_raised(error))


def commit_turn(ports: TurnPorts, attempt_id: UUID) -> None:
    """`session_commit`: commit the trees, store the reply, close and bill the turn."""
    turn = read_turn(ports, attempt_id)
    if turn is None:
        return
    ctx = turn.ctx
    try:
        update = _closing(turn)
    except Exception as error:
        log.exception(COMMIT_FAILED, run_id=str(turn.run.id), attempt=ctx.attempt.n)
        update = {"status": "error", "output_ref": _raised(error)}
    finished = ctx.attempt.model_copy(update={**update, "ended_at": ctx.ports.clock.now()})
    committed(ctx, lambda attempts: attempts.mark_finished(finished))
    if ctx.ports.spend_writes is None:
        return
    with ctx.ports.spend_writes() as spend_ports:
        record_attempt_spend(spend_ports, turn.run, finished, None, locked=True)


def _closing(turn: Turn) -> dict[str, Any]:
    """The finish half's fields: the commit's outcome, the reply and the end SHAs."""
    ctx, attempt = turn.ctx, turn.ctx.attempt
    update: dict[str, Any] = {}
    if attempt.status in UNRUN:
        update = {"status": "error", "output_ref": attempt.output_ref or INTERRUPTED}
    if turn.run.status not in TERMINAL_RUN:
        message = session.TURN_MESSAGE.format(k=session.turn_number(turn.turns, attempt))
        try:
            agent_workdir.sweep(ctx, message)
        except GitError as error:
            update = {"status": "error", "output_ref": session_dispatch.git_words(error)}
    workspace = require_workspace(ctx, str(agent_workdir.tree(ctx)))
    reply = session.capped(read_decision(workspace, session.REPLY_FILE))
    return {**update, **agent_workdir.end_shas(ctx), "reply": reply}


def _close(writers: WriterPorts, attempt: Attempt, reason: str) -> None:
    with writers.uow:
        closed = attempt.model_copy(
            update={"status": "error", "output_ref": reason, "ended_at": writers.clock.now()}
        )
        writers.attempts.mark_finished(closed)
        writers.uow.commit()


def _raised(error: Exception) -> str:
    return RAISED.format(name=type(error).__name__, message=error)


def _text(value: object) -> str | None:
    return str(value) if value else None
