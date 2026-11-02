"""The Operator's senior session, as rules: who holds the Run, which attempts are the
session's, and which of their changes are anchor edits (AD-21, AD-23).

Pure. `use_cases/session_checks.py` reads the trees and the registry; everything it asks
of what it read is answered here. The table's predicates for the terminal and senior
sessions live here too, beside the facts they turn on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, Literal, get_args

from orchestrator.application.rules import protected_paths
from orchestrator.application.rules.frames import epic_frame, run_is_one_epic, story_frame
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Change
from orchestrator.domain.statuses import AttemptRole, SignalKind
from orchestrator.domain.values import Signal

SESSION_ROLE: AttemptRole = "session"
SESSION_START: SignalKind = "session_start"

#: The context a session opens with: the parked Story, its epic, or the whole Run.
SessionScope = Literal["story", "epic", "run"]
SCOPES: tuple[SessionScope, ...] = get_args(SessionScope)

SCOPE_KEY = "scope"
HARNESS_KEY = "harness"
MODEL_KEY = "model"
CONFIRMED_KEY = "confirmed_paths"
#: How many session attempts the close's anchor check read; the effect re-counts under the
#: row lock, so a turn that started in between refuses the close.
TURNS_KEY = "turns"

ENDED_CONFIRMED = "senior session ended; confirmed: {paths}"


def no_open_session(
    run: Run, _row: StepRun | None, _signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    """`session_start` and `terminal_start` refuse each other (AD-13, 2026-11-01)."""
    return not run.terminal_session and not run.senior_session


def in_terminal_session(
    run: Run, _row: StepRun | None, _signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    return run.terminal_session


def can_start_session(
    run: Run, row: StepRun | None, signal: Signal, rows: Sequence[StepRun]
) -> bool:
    """A session works on the parked row, so a stop that names none offers none."""
    return run.park_path is not None and no_open_session(run, row, signal, rows)


def in_senior_session(
    run: Run, _row: StepRun | None, _signal: Signal, _rows: Sequence[StepRun]
) -> bool:
    return run.senior_session


def last_start(records: Sequence[GateRecord]) -> GateRecord | None:
    return next((record for record in reversed(records) if record.event == SESSION_START), None)


def last_start_payload(records: Sequence[GateRecord]) -> dict[str, Any]:
    start = last_start(records)
    return dict(start.payload) if start is not None else {}


def session_attempts(
    attempts: Iterable[Attempt], records: Sequence[GateRecord]
) -> tuple[Attempt, ...]:
    """The `session` attempts started at or after the Run's last `session_start` record."""
    start = last_start(records)
    if start is None:
        return ()
    return tuple(
        attempt
        for attempt in attempts
        if attempt.role == SESSION_ROLE
        and attempt.started_at is not None
        and attempt.started_at >= start.at
    )


def first_shas(attempts: Sequence[Attempt]) -> tuple[str | None, str | None]:
    """The first `start_sha` and the first `root_start_sha` the session recorded."""
    start = next((a.start_sha for a in attempts if a.start_sha is not None), None)
    root = next((a.root_start_sha for a in attempts if a.root_start_sha is not None), None)
    return start, root


def turn_open(attempts: Sequence[Attempt]) -> bool:
    return any(attempt.ended_at is None for attempt in attempts)


def anchor_edits(changes: Sequence[Change], anchors: frozenset[str]) -> tuple[Change, ...]:
    """AD-17's anchors among the changes, with no frozen tests and nothing accepted (AD-23)."""
    return protected_paths.check(changes, anchors, ())


def scopes_at(park_path: str | None, rows: Sequence[StepRun]) -> tuple[SessionScope, ...]:
    """The scopes a session opened at `park_path` has a frame for, in `SCOPES` order."""
    if park_path is None:
        return ()
    found: list[SessionScope] = []
    if story_frame(park_path) is not None:
        found.append("story")
    if epic_frame(park_path) is not None or run_is_one_epic(rows):
        found.append("epic")
    found.append("run")
    return tuple(found)


def confirmed_paths(payload: dict[str, Any]) -> tuple[str, ...]:
    """The files a close confirmed; anything but a list confirms none."""
    supplied = payload.get(CONFIRMED_KEY)
    if not isinstance(supplied, list | tuple):
        return ()
    return tuple(str(entry) for entry in supplied)


def ended_text(payload: dict[str, Any]) -> str | None:
    confirmed = confirmed_paths(payload)
    if not confirmed:
        return None
    return ENDED_CONFIRMED.format(paths=", ".join(confirmed))
