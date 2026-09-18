"""`list_queue` (SPEC CAP-11, FR-13, FR-25, AD-12): the queue as the engine sees it.

`GET /queue` answers one question the Board and the Run screen do not: *why is nothing
happening?* The engine's own `list_queue()` (4.6) says which Runs it is holding and their
raw `enqueued`/`pending` state; this module joins that against `run` and `step_run` to say,
in the Operator's own words, why each one waits — `reason` is always one of the four fixed
sentences AD-12 states, never a paraphrase.

**The three reasons that are not `waiting for your answer`.** A `needs_you` Run always
reads `waiting for your answer`, whatever the engine's own state says (its workflow is still
`pending` there, mid-`recv` — AD-12 holds its partition and its slot for that whole wait). A
`pending` Run that is not parked is simply `running`. An `enqueued` Run waits behind
something concrete: another non-terminal Run already holds its Repository's partition
(`repository lock held by {label}`), or every partition is free but the queue's own global
concurrency ceiling is not (`global concurrency, held by {label1}, {label2}`) — the same
two facts `application/preflight/checks.py::queue_note` already computes for *a Run that
does not exist yet*; this module answers the same question for one that does, in the fixed
words this endpoint promises rather than that one's prose.

**Ordering (AD-12): active first, then queued by position.** `running` sorts first,
`waiting for your answer` last — a parked Run holds its slot but is not advancing, so it
reads behind every Run that is — and the enqueued rows in between sort by the engine's own
position, ascending.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from orchestrator.application.preflight.checks import run_label
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import QueueEntry, WorkflowEngine
from orchestrator.domain.ports.repositories import RunRepository, StepRunRepository

#: The fixed reasons (SPEC CAP-11, AD-12). A queue row states one of these, verbatim.
REASON_RUNNING = "running"
REASON_WAITING_ANSWER = "waiting for your answer"
# operator revision 2026-09-15: partition by (repository, branch)
REASON_BRANCH_HELD = "branch held by {run}"
REASON_GLOBAL_CONCURRENCY = "global concurrency, held by {runs}"
#: A saved Run: persisted but not yet enqueued (story 5-3, AD-6).
REASON_SAVED = "saved — not started"

#: The engine's own two states for a held workflow (`domain/ports/engine.py::QueueState`).
PENDING = "pending"


@dataclass(frozen=True)
class QueueRow:
    """One row of `GET /queue`: a Run the engine is holding, and why it waits."""

    position: int | None
    run: Run
    next_step_label: str
    reason: str
    waiting_since: datetime
    waiting_seconds: float


@dataclass(frozen=True)
class QueueView:
    """The whole queue: every row the engine holds, plus the concurrency ceiling."""

    items: list[QueueRow]
    max_active_runs: int


@dataclass(frozen=True)
class QueuePorts:
    """What `list_queue` reads: the engine, the two repositories it joins against, a clock."""

    engine: WorkflowEngine
    runs: RunRepository
    steps: StepRunRepository
    clock: Clock
    max_active_runs: int


def list_queue(ports: QueuePorts) -> QueueView:
    """Every Run the engine is holding, joined with its rows for the reason it waits."""
    engine_entries = list(ports.engine.list_queue())
    # IDs already in the engine queue — they must not also appear as saved rows.
    engine_run_ids: frozenset[UUID] = frozenset(entry.run_id for entry in engine_entries)
    rows = [row for row in (_row(ports, entry) for entry in engine_entries) if row is not None]
    rows += [_saved_row(ports, r) for r in _saved_runs(ports.runs, engine_run_ids)]
    return QueueView(items=sorted(rows, key=_order_key), max_active_runs=ports.max_active_runs)


def _order_key(row: QueueRow) -> tuple[int, int]:
    """Active first, then queued by position; a parked Run last; saved runs after that."""
    if row.reason == REASON_RUNNING:
        return (0, 0)
    if row.position is not None:
        return (1, row.position)
    if row.reason == REASON_SAVED:
        return (3, 0)
    return (2, 0)


def _saved_runs(runs: RunRepository, engine_run_ids: frozenset[UUID]) -> list[Run]:
    """All queued Runs not yet sent to the engine (engine_ref == {} and not in engine queue)."""
    return [
        r for r in runs.list_by_status("queued") if not r.engine_ref and r.id not in engine_run_ids
    ]


def _saved_row(ports: QueuePorts, run: Run) -> QueueRow:
    """One saved Run as a `QueueRow`, with position=None and reason=REASON_SAVED."""
    steps = ports.steps.list_for_run(run.id)
    return QueueRow(
        position=None,
        run=run,
        next_step_label=_next_step_label(run, steps),
        reason=REASON_SAVED,
        waiting_since=run.created_at,
        waiting_seconds=(ports.clock.now() - run.created_at).total_seconds(),
    )


def _row(ports: QueuePorts, entry: QueueEntry) -> QueueRow | None:
    """One engine entry, joined — `None` for a Run the engine still names but is gone."""
    run = ports.runs.get(entry.run_id)
    if run is None:
        return None
    steps = ports.steps.list_for_run(run.id)
    reason, position = _reason(ports, run, entry)
    return QueueRow(
        position=position,
        run=run,
        next_step_label=_next_step_label(run, steps),
        reason=reason,
        waiting_since=entry.enqueued_at,
        waiting_seconds=(ports.clock.now() - entry.enqueued_at).total_seconds(),
    )


def _reason(ports: QueuePorts, run: Run, entry: QueueEntry) -> tuple[str, int | None]:
    """The fixed sentence this row states, and the position it keeps beside it."""
    if run.status == "needs_you":
        return REASON_WAITING_ANSWER, None
    if entry.engine_state == PENDING:
        return REASON_RUNNING, None
    holder = _holding_run(ports.runs, run)
    if holder is not None:
        return REASON_BRANCH_HELD.format(run=run_label(holder)), entry.position
    runs_labels = ", ".join(run_label(candidate) for candidate in _active_runs(ports.runs))
    return REASON_GLOBAL_CONCURRENCY.format(runs=runs_labels), entry.position


def _holding_run(runs: RunRepository, run: Run) -> Run | None:
    """The other non-terminal Run on this Repository with the same partition branch, if any.

    Skips Runs where either side has `partition_branch = None` — old runs without the field
    (story 5-1) are treated as non-competing (operator revision 2026-09-15).
    """
    if run.partition_branch is None:
        return None
    return next(
        (
            r
            for r in runs.list_by_repository_non_terminal(run.repository_id)
            if r.id != run.id
            and r.partition_branch is not None
            and r.partition_branch == run.partition_branch
        ),
        None,
    )


def _active_runs(runs: RunRepository) -> list[Run]:
    """Every Run occupying a global-concurrency slot: running, or parked mid-wait (AD-12)."""
    return [*runs.list_by_status("running"), *runs.list_by_status("needs_you")]


def _next_step_label(run: Run, steps: Sequence[StepRun]) -> str:
    """The row the Operator would point at right now: parked, running, queued, then planned.

    The same question `application/use_cases/project_runs.py::_current_step_label` answers
    for the Board — duplicated rather than imported, the way `_reason` is duplicated between
    `application/preflight/checks.py` and `application/use_cases/clone_check.py`: each
    reader's own small pure function, not a cross-module dependency for a handful of lines.
    A queued Run adds one case that module never needs — every row still `planned` — because
    a Run this early in the queue has not started its first one yet.
    """
    if not steps:
        return ""
    if run.park_path is not None:
        parked = next((row for row in steps if row.path == run.park_path), None)
        if parked is not None:
            return parked.label
    running = next((row for row in steps if row.status == "running"), None)
    if running is not None:
        return running.label
    queued = next((row for row in steps if row.status == "queued"), None)
    if queued is not None:
        return queued.label
    planned = next((row for row in steps if row.status == "planned"), None)
    if planned is not None:
        return planned.label
    touched = [row for row in steps if row.status != "planned"]
    return touched[-1].label if touched else steps[0].label
