"""`GET /runs/{id}/session`: the Operator's senior session as one Run reads it (AD-23).

Writes nothing. `available` is the table's own answer for `session_start` here, so the
screen offers a start exactly when the signal would pass `validate`; the start's live
checks (registry, Probe, worktree, budget) still answer the POST itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules import session
from orchestrator.application.rules.signals import row_at, validate
from orchestrator.application.use_cases import session_checks
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.writers import require_run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ports.git import Change
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import Signal


@dataclass(frozen=True)
class SessionView:
    active: bool
    available: bool
    scopes: tuple[session.SessionScope, ...]
    scope: session.SessionScope | None
    harness: str | None
    model: str | None
    anchor_edits: tuple[Change, ...]


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
    return SessionView(
        active=active,
        available=available,
        scopes=session.scopes_at(run.park_path, rows) if run.status == "needs_you" else (),
        scope=_scope(started.get(session.SCOPE_KEY)),
        harness=_text(started.get(session.HARNESS_KEY)),
        model=_text(started.get(session.MODEL_KEY)),
        anchor_edits=session_checks.anchor_edits(ports, run, rows, row) if active else (),
    )


def _scope(value: object) -> session.SessionScope | None:
    return next((scope for scope in session.SCOPES if scope == value), None)


def _text(value: object) -> str | None:
    return str(value) if value is not None else None
