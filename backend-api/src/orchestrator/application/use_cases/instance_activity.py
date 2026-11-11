"""`read_activity` (SPEC CAP-3, AD-30): what the instance is doing right now.

The upgrade script reads this before it stops anything. A step is *working* when its row is
`running`, or when a `session` or `consult` attempt of it is open; a consult opens on a row
`start_attempt` has already set `running`, so the two are one entry, never two. A Run is *in
the engine* when it is non-terminal and holds an `engine_ref` — the same test
`use_cases/queue.py::_saved_runs` uses to tell a saved Run from an enqueued one — and its
`queue_reason` is `list_queue`'s own sentence, never re-derived here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from orchestrator.application.preflight.checks import run_label
from orchestrator.application.use_cases.queue import QueuePorts, list_queue
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.repositories import AttemptRepository
from orchestrator.domain.statuses import ParkKind, RunStatus

_ENGINE_STATUSES: tuple[RunStatus, ...] = ("queued", "running", "needs_you")


@dataclass(frozen=True)
class WorkingStep:
    run_id: UUID
    run_label: str
    path: str
    kind: str
    started_at: datetime | None


@dataclass(frozen=True)
class EngineRun:
    run_id: UUID
    run_label: str
    status: RunStatus
    park_kind: ParkKind | None
    queue_reason: str | None


@dataclass(frozen=True)
class HoldView:
    held_at: datetime
    expires_at: datetime
    reason: str


@dataclass(frozen=True)
class InstanceActivity:
    working: list[WorkingStep]
    in_engine: list[EngineRun]
    hold: HoldView | None
    dbos_application_version: str


@dataclass(frozen=True)
class ActivityPorts:
    queue: QueuePorts
    attempts: AttemptRepository
    dbos_application_version: str


def read_activity(ports: ActivityPorts) -> InstanceActivity:
    """The working steps and the engine's Runs. Writes nothing."""
    return InstanceActivity(
        working=_working(ports),
        in_engine=_in_engine(ports),
        hold=None,
        dbos_application_version=ports.dbos_application_version,
    )


def _working(ports: ActivityPorts) -> list[WorkingStep]:
    open_attempts = ports.attempts.list_open()
    running = ports.queue.steps.list_running()
    running_ids = {row.id for row in running}
    found: list[WorkingStep] = []
    for row in running:
        run = ports.queue.runs.get(row.run_id)
        if run is None:
            continue
        attempt = _latest_open(open_attempts, row)
        kind = attempt.role if attempt is not None and attempt.role != "agent" else row.kind
        found.append(
            WorkingStep(
                run_id=run.id,
                run_label=run_label(run),
                path=row.path,
                kind=kind,
                started_at=None if attempt is None else attempt.started_at,
            )
        )
    for attempt in open_attempts:
        if attempt.role == "agent" or attempt.step_run_id in running_ids:
            continue
        run = ports.queue.runs.get(attempt.run_id)
        turn_row = next(
            (
                r
                for r in ports.queue.steps.list_for_run(attempt.run_id)
                if r.id == attempt.step_run_id
            ),
            None,
        )
        if run is None or turn_row is None:
            continue
        found.append(
            WorkingStep(
                run_id=run.id,
                run_label=run_label(run),
                path=turn_row.path,
                kind=attempt.role,
                started_at=attempt.started_at,
            )
        )
    return sorted(found, key=_working_order)


def _latest_open(open_attempts: list[Attempt], row: StepRun) -> Attempt | None:
    mine = [a for a in open_attempts if a.step_run_id == row.id]
    return max(mine, key=lambda a: a.n, default=None)


def _working_order(step: WorkingStep) -> tuple[bool, datetime | None, str]:
    # `None` sorts last; the datetime slot is only compared between two started steps.
    return (step.started_at is None, step.started_at, step.path)


def _in_engine(ports: ActivityPorts) -> list[EngineRun]:
    reasons = {item.run.id: item.reason for item in list_queue(ports.queue).items}
    runs: list[Run] = [
        run
        for status in _ENGINE_STATUSES
        for run in ports.queue.runs.list_by_status(status)
        if run.engine_ref
    ]
    runs.sort(key=lambda run: (run.created_at, str(run.id)))
    return [
        EngineRun(
            run_id=run.id,
            run_label=run_label(run),
            status=run.status,
            park_kind=run.park_kind,
            queue_reason=reasons.get(run.id),
        )
        for run in runs
    ]
