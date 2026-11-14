"""Queueing a Run's metrics calculation, asking for one by hand, and the start-up net.

Nothing here talks to the engine inside a unit of work: the row is added in the writer's own
transaction and the engine is told after the commit (AD-8, AD-6).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.domain.entities.metric_results import INTERRUPTED, MetricCalculation
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.metric_results import (
    MetricCalculationRepository,
    ResultVersionRepository,
)
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.statuses import TERMINAL_RUN

NOT_ENDED = "run {run_id} is {status}; metrics are calculated on an ended Run"
IN_PROGRESS = "calculation v{n} is {state}"


@dataclass(frozen=True)
class CalculatePorts:
    runs: RunRepository
    calculations: MetricCalculationRepository
    versions: ResultVersionRepository
    engine: WorkflowEngine
    clock: Clock
    uow: UnitOfWork


def queue_terminal_calculation(
    calculations: MetricCalculationRepository | None,
    versions: ResultVersionRepository | None,
    clock: Clock,
    before: Run,
    after: Run,
) -> None:
    """Add the `at_attempt_end` calculation when this write takes the Run to a terminal status."""
    if calculations is None or versions is None:
        return
    if before.status in TERMINAL_RUN or after.status not in TERMINAL_RUN:
        return
    # a writer that read the Run unlocked can race a committed cancel past the guard above
    if calculations.active_for_run(after.id) is not None:
        return
    calculations.add(
        MetricCalculation(
            id=new_id(),
            run_id=after.id,
            target_n=versions.next_n(after.id),
            state="queued",
            entry_point=("at_attempt_end",),
            queued_at=clock.now(),
        )
    )


def enqueue_queued(
    engine: WorkflowEngine | None,
    calculations: MetricCalculationRepository | None,
    run: Run,
) -> None:
    """After the commit: hand the Run's queued calculation to the engine."""
    if engine is None or calculations is None or run.status not in TERMINAL_RUN:
        return
    active = calculations.active_for_run(run.id)
    if active is not None and active.state == "queued":
        engine.enqueue_calculation(active.id)


def request_calculation(ports: CalculatePorts, run_id: UUID) -> MetricCalculation:
    """A manual calculation of an ended Run; 404 unknown, 409 when not ended or one is active."""
    with ports.uow:
        run = ports.runs.get_for_update(run_id)
        if run is None:
            raise NotFound(f"no run {run_id}")
        if run.status not in TERMINAL_RUN:
            raise Conflict(NOT_ENDED.format(run_id=run_id, status=run.status))
        active = ports.calculations.active_for_run(run_id)
        if active is not None:
            raise Conflict(IN_PROGRESS.format(n=active.target_n, state=active.state))
        calculation = MetricCalculation(
            id=new_id(),
            run_id=run_id,
            target_n=ports.versions.next_n(run_id),
            state="queued",
            entry_point=("manual",),
            queued_at=ports.clock.now(),
        )
        ports.calculations.add(calculation)
        ports.uow.commit()
    ports.engine.enqueue_calculation(calculation.id)
    return calculation


def sweep_calculations(
    calculations: MetricCalculationRepository,
    uow: UnitOfWork,
    clock: Clock,
    engine: WorkflowEngine,
    held: frozenset[UUID],
) -> None:
    """At start-up: a `running` calculation the engine does not hold is `interrupted`; a
    `queued` one it does not hold is enqueued again."""
    with uow:
        for calculation in calculations.list_by_state("running"):
            if calculation.id not in held:
                calculations.set(
                    calculation.model_copy(
                        update={"state": "failed", "output": INTERRUPTED, "ended_at": clock.now()}
                    )
                )
        queued = [c for c in calculations.list_by_state("queued") if c.id not in held]
        uow.commit()
    for calculation in queued:
        engine.enqueue_calculation(calculation.id)
