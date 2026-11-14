"""`read_activity` (SPEC CAP-3, AD-30): what the instance is doing right now.

The upgrade script reads this before it stops anything. A step is *working* when its row is
`running`, or when a `session` or `consult` attempt of it is open; a consult opens on a row
`start_attempt` has already set `running`, so the two are one entry, never two. A row or an
attempt of a terminal Run (`done`, `failed`, `cancelled`) is never working: cancel kills the
process group but leaves started rows `running` (AD-8 keeps that writer as it is), so the read
skips them, including rows earlier cancellations already left behind. A Run is *in
the engine* when it is non-terminal and holds an `engine_ref` — the same test
`use_cases/queue.py::_saved_runs` uses to tell a saved Run from an enqueued one — and its
`queue_reason` is `list_queue`'s own sentence, never re-derived here. The active hold is read
here too, unlocked.
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
from orchestrator.domain.ports.metric_results import MetricCalculationRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.statuses import TERMINAL_RUN, ParkKind, RunStatus

CALCULATION_KIND = "calculation"
CALCULATION_PATH = "metrics v{n}"

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
    calculations: MetricCalculationRepository | None = None


def read_activity(ports: ActivityPorts) -> InstanceActivity:
    """The working steps, the engine's Runs and the active hold. Writes nothing."""
    holds = ports.queue.holds
    stored = None if holds is None else holds.get()
    active = stored is not None and stored.active(ports.queue.clock.now())
    return InstanceActivity(
        working=working_steps(
            ports.queue.runs, ports.queue.steps, ports.attempts, ports.calculations
        ),
        in_engine=_in_engine(ports),
        hold=HoldView(stored.held_at, stored.expires_at, stored.reason)
        if stored is not None and active
        else None,
        dbos_application_version=ports.dbos_application_version,
    )


def working_steps(
    runs: RunRepository,
    steps: StepRunRepository,
    attempts: AttemptRepository,
    calculations: MetricCalculationRepository | None = None,
) -> list[WorkingStep]:
    open_attempts = attempts.list_open()
    running = steps.list_running()
    running_ids = {row.id for row in running}
    found: list[WorkingStep] = []
    for row in running:
        run = runs.get(row.run_id)
        if run is None or run.status in TERMINAL_RUN:
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
        run = runs.get(attempt.run_id)
        turn_row = next(
            (r for r in steps.list_for_run(attempt.run_id) if r.id == attempt.step_run_id),
            None,
        )
        if run is None or run.status in TERMINAL_RUN or turn_row is None:
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
    for calculation in [] if calculations is None else calculations.list_by_state("running"):
        run = runs.get(calculation.run_id)
        if run is not None:
            found.append(
                WorkingStep(
                    run_id=run.id,
                    run_label=run_label(run),
                    path=CALCULATION_PATH.format(n=calculation.target_n),
                    kind=CALCULATION_KIND,
                    started_at=calculation.started_at,
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
