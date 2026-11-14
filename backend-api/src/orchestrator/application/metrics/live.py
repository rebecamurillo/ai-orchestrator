"""Values so far on a live Run: the same methods over the current facts, nothing stored."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.metrics.compute import compute
from orchestrator.application.metrics.inputs import AttemptInputs, RunInputs, choose_fact_set
from orchestrator.application.metrics.roles import role_of
from orchestrator.application.metrics.values import MetricValue
from orchestrator.application.use_cases.spend_figures import first_fact_money
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository, GatewayReadRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.run_records import RunRepositoryRecords


@dataclass(frozen=True)
class MetricsReadPorts:
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    records: GateRecordRepository
    fact_sets: FactSetRepository
    gateway_reads: GatewayReadRepository
    run_records: RunRepositoryRecords
    clock: Clock


def load_inputs(ports: MetricsReadPorts, run_id: UUID) -> RunInputs:
    run = ports.runs.get(run_id)
    if run is None:
        raise LookupError(f"no run {run_id}")
    rows = sorted(ports.steps.list_for_run(run_id), key=lambda r: r.seq)
    attempts: list[AttemptInputs] = []
    for row in rows:
        for attempt in ports.attempts.list_for_row(row.id):
            chosen = choose_fact_set(ports.fact_sets.list_for_attempt(attempt.id))
            reads = tuple(
                (read, ports.gateway_reads.usage(read.id))
                for read in sorted(
                    ports.gateway_reads.list_for_attempt(attempt.id),
                    key=lambda r: r.read_at,
                    reverse=True,
                )
            )
            attempts.append(
                AttemptInputs(
                    attempt,
                    row,
                    role_of(attempt, row),
                    reads,
                    chosen,
                    ports.fact_sets.rows(chosen.id) if chosen else None,
                    first_fact_money(ports.fact_sets, attempt.id),
                )
            )
    return RunInputs(
        run=run,
        rows=rows,
        attempts=attempts,
        records=ports.records.list_for_run(run_id),
        now=ports.clock.now(),
        run_repositories=ports.run_records.list_for_run(run_id),
    )


def live_values(ports: MetricsReadPorts, run_id: UUID) -> list[MetricValue]:
    return compute(load_inputs(ports, run_id))
