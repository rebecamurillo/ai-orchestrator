"""`GET /runs/{id}/session`: the Operator's senior session as one Run reads it, its turns
included (AD-23).

Writes nothing. `available` is the table's own answer for `session_start` here, so the
screen offers a start exactly when the signal would pass `validate`; the start's live
checks (registry, Probe, worktree, budget) still answer the POST itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import row_at, validate
from orchestrator.application.use_cases import session_checks
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.writers import require_run
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.git import Change
from orchestrator.domain.statuses import TERMINAL_RUN, StepStatus
from orchestrator.domain.values import Signal


@dataclass(frozen=True)
class SessionTurn:
    """One `session` attempt, numbered from 1 within its session."""

    attempt_id: UUID
    turn: int
    status: StepStatus
    message: str
    reply: str
    started_at: datetime | None
    ended_at: datetime | None
    exit_code: int | None
    cost_usd: Decimal | None


@dataclass(frozen=True)
class SessionView:
    active: bool
    available: bool
    scopes: tuple[session.SessionScope, ...]
    scope: session.SessionScope | None
    harness: str | None
    model: str | None
    anchor_edits: tuple[Change, ...]
    turn_running: bool = False
    turns: tuple[SessionTurn, ...] = ()


def turn_of(attempt: Attempt, turn: int) -> SessionTurn:
    return SessionTurn(
        attempt_id=attempt.id,
        turn=turn,
        status=attempt.status,
        message=attempt.message,
        reply=attempt.reply,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        exit_code=attempt.exit_code,
        cost_usd=attempt.cost_usd,
    )


def turns_of(attempts: Sequence[Attempt]) -> tuple[SessionTurn, ...]:
    ordered = sorted(attempts, key=lambda attempt: attempt.n)
    return tuple(turn_of(attempt, k) for k, attempt in enumerate(ordered, start=1))


def session_view(ports: SessionPorts, run_id: UUID) -> SessionView:
    """The session's state; its payload is the last `session_start` record's (AD-23)."""
    run = require_run(ports.writers, run_id)
    rows = ports.writers.steps.list_for_run(run_id)
    row = row_at(rows, run.park_path)
    active = run.senior_session and run.status not in TERMINAL_RUN
    try:
        validate(run, row, Signal(kind="session_start"), rows)
        available = True
    except Conflict:
        available = False
    started = session.last_start_payload(ports.writers.records.list_for_run(run_id))
    turns = session_checks.turns(ports, run, row)
    return SessionView(
        active=active,
        available=available,
        scopes=session.scopes_at(run.park_path, rows) if run.status == "needs_you" else (),
        scope=_scope(started.get(session.SCOPE_KEY)),
        harness=_text(started.get(session.HARNESS_KEY)),
        model=_text(started.get(session.MODEL_KEY)),
        anchor_edits=session_checks.anchor_edits(ports, run, rows, row) if active else (),
        turn_running=session.turn_open(turns),
        turns=turns_of(turns),
    )


def _scope(value: object) -> session.SessionScope | None:
    return next((scope for scope in session.SCOPES if scope == value), None)


def _text(value: object) -> str | None:
    return str(value) if value is not None else None
