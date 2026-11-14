"""The metrics calculation job (SPEC CAP-5, RM-3), in the two halves the engine workflow runs.

`begin_calculation` decides whether the calculation may start now; `run_calculation` does the
work and writes one immutable result version, or marks the calculation `failed` and writes
nothing else. Neither reads or writes a Run, step or attempt status.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal
from uuid import UUID

import structlog

from orchestrator.application.analysis.run_analysis import load_code, pending_analyses
from orchestrator.application.metrics.compute import compute
from orchestrator.application.metrics.live import MetricsReadPorts, load_inputs
from orchestrator.application.metrics.methods import REGISTRY
from orchestrator.application.metrics.step_values import not_catalogued, step_values
from orchestrator.application.metrics.versions import carry_forward, origin_of, to_stored
from orchestrator.application.use_cases.instance_hold import hold_active
from orchestrator.application.use_cases.record_attempt_facts import (
    FactsPorts,
    record_attempt_facts,
)
from orchestrator.application.use_cases.spend import SpendPorts, reread_gateway_for_run
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.facts import GatewayTrigger
from orchestrator.domain.entities.metric_results import (
    EntryPoint,
    MetricCalculation,
    ResultVersion,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.facts import FactSetRepository, GatewayReadRepository
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.domain.ports.instance_hold import InstanceHoldRepository
from orchestrator.domain.ports.log_facts import LogFacts
from orchestrator.domain.ports.metric_results import (
    MetricCalculationRepository,
    ResultVersionRepository,
)
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.run_records import RunRepositoryRecords
from orchestrator.domain.ports.unit_of_work import UnitOfWork

log = structlog.get_logger(__name__)

CALCULATION_FAILED = "metrics calculation failed"

Begin = Literal["started", "held", "waiting", "skip"]


@dataclass(frozen=True)
class CalculationPorts:
    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    records: GateRecordRepository
    holds: InstanceHoldRepository | None
    calculations: MetricCalculationRepository
    versions: ResultVersionRepository
    fact_sets: FactSetRepository
    gateway_reads: GatewayReadRepository
    run_records: RunRepositoryRecords
    gateway: Gateway
    extractors: Mapping[str, LogFacts]
    log_exists: Callable[[str], bool]
    clock: Clock
    uow: UnitOfWork
    analyses: AnalysisRepository | None = None
    #: `(run_id, calculation_id)`: analyse every repository of the Run under that calculation.
    analysis: Callable[[UUID, UUID], Sequence[Analysis]] | None = None

    def facts_ports(self) -> FactsPorts:
        return FactsPorts(
            facts=self.fact_sets,
            uow=self.uow,
            clock=self.clock,
            extractors=self.extractors,
            log_exists=self.log_exists,
            subscription_auth=None,
        )

    def spend_ports(self) -> SpendPorts:
        return SpendPorts(
            gateway=self.gateway,
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            gateway_reads=self.gateway_reads,
            clock=self.clock,
            uow=self.uow,
            fact_sets=self.fact_sets,
        )

    def read_ports(self) -> MetricsReadPorts:
        return MetricsReadPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            records=self.records,
            fact_sets=self.fact_sets,
            gateway_reads=self.gateway_reads,
            run_records=self.run_records,
            clock=self.clock,
        )


def _attempts_of(ports: CalculationPorts, run_id: UUID) -> list[Attempt]:
    return [
        attempt
        for row in ports.steps.list_for_run(run_id)
        for attempt in ports.attempts.list_for_row(row.id)
    ]


def begin_calculation(ports: CalculationPorts, calculation_id: UUID) -> Begin:
    """Start the calculation when nothing holds or awaits it; otherwise say why not."""
    with ports.uow:
        calculation = ports.calculations.get(calculation_id)
        if calculation is None or calculation.state != "queued":
            return "skip"
        now = ports.clock.now()
        if hold_active(ports.holds, now):
            return "held"
        attempts = _attempts_of(ports, calculation.run_id)
        if any(a.harness and a.ended_at is None for a in attempts):
            return "waiting"
        ports.calculations.set(
            calculation.model_copy(update={"state": "running", "started_at": now})
        )
        ports.uow.commit()
    return "started"


def run_calculation(ports: CalculationPorts, calculation_id: UUID) -> None:
    """Calculate and store the version. Never raises: a failure is the calculation's state."""
    try:
        with ports.uow:
            calculation = ports.calculations.get(calculation_id)
        if calculation is None or calculation.state != "running":
            return
        _calculate(ports, calculation)
    except Exception as error:
        log.exception(CALCULATION_FAILED, calculation_id=str(calculation_id))
        fail_calculation(ports, calculation_id, f"{type(error).__name__}: {error}")


def fail_calculation(ports: CalculationPorts, calculation_id: UUID, output: str) -> None:
    """Mark the calculation `failed` with `output`; nothing else is written."""
    with ports.uow:
        calculation = ports.calculations.get(calculation_id)
        if calculation is None:
            return
        ports.calculations.set(
            calculation.model_copy(
                update={"state": "failed", "output": output, "ended_at": ports.clock.now()}
            )
        )
        ports.uow.commit()


def _refresh_facts(ports: CalculationPorts, run_id: UUID) -> None:
    """Record facts for attempts without any, and again where a newer extractor can read a log."""
    with ports.uow:
        attempts = [a for a in _attempts_of(ports, run_id) if a.harness and a.ended_at]
        stored = {a.id: ports.fact_sets.list_for_attempt(a.id) for a in attempts}
    for attempt in attempts:
        sets = stored[attempt.id]
        extractor = ports.extractors.get(attempt.harness or "")
        if not sets:
            record_attempt_facts(ports.facts_ports(), attempt)
            continue
        if extractor is None or attempt.log_path is None:
            continue
        seen = max((s.extractor_version for s in sets if s.extractor == extractor.name), default=0)
        if extractor.version > seen and ports.log_exists(attempt.log_path):
            record_attempt_facts(ports.facts_ports(), attempt)


def _analyses(ports: CalculationPorts, calculation: MetricCalculation) -> list[Analysis]:
    """A manual calculation analyses afresh; every other reads what the workflow step stored."""
    if "manual" in calculation.entry_point and ports.analysis is not None:
        return list(ports.analysis(calculation.run_id, calculation.id))
    if ports.analyses is None:
        return []
    with ports.uow:
        return pending_analyses(ports.analyses.list_for_run(calculation.run_id), calculation.run_id)


def _entry_point(
    calculation: MetricCalculation, found: Sequence[Analysis]
) -> tuple[EntryPoint, ...]:
    """The workflow step is an entry point only when pending analyses fed the version."""
    pending = any(a.calculation_id is None for a in found)
    if pending and "workflow_step" not in calculation.entry_point:
        return (*calculation.entry_point, "workflow_step")
    return calculation.entry_point


def _fingerprint(found: Sequence[Analysis]) -> str | None:
    distinct = sorted({a.toolset_fingerprint for a in found})
    if not distinct:
        return None
    return hashlib.sha256("\n".join(distinct).encode()).hexdigest()


def _calculate(ports: CalculationPorts, calculation: MetricCalculation) -> None:
    run_id = calculation.run_id
    _refresh_facts(ports, run_id)
    trigger: GatewayTrigger = "run_end" if calculation.target_n == 1 else "recalculation"
    reread_gateway_for_run(ports.spend_ports(), run_id, trigger)
    found = _analyses(ports, calculation)
    with ports.uow:
        inputs = load_inputs(ports.read_ports(), run_id)
        if ports.analyses is not None:
            inputs = replace(inputs, code=load_code(ports.analyses, found))
        earlier = [
            (v.n, ports.versions.values(v.id))
            for v in reversed(ports.versions.list_for_run(run_id))
        ]
    declared = step_values(inputs.code)
    values = [*carry_forward(compute(inputs), earlier), *declared]
    version = ResultVersion(
        id=new_id(),
        run_id=run_id,
        n=calculation.target_n,
        calculated_at=ports.clock.now(),
        entry_point=_entry_point(calculation, found),
        methods=tuple(sorted({*REGISTRY, *(v.method_id for v in declared)})),
        fact_set_ids=tuple(sorted(a.fact_set.id for a in inputs.attempts if a.fact_set)),
        analysis_ids=tuple(a.id for a in found),
        toolset_fingerprint=_fingerprint(found),
    )
    stored = [to_stored(v, version.id, origin_of(v, inputs)) for v in values]
    with ports.uow:
        ports.versions.add(version, stored)
        ports.calculations.set(
            calculation.model_copy(
                update={
                    "state": "done",
                    "ended_at": ports.clock.now(),
                    "output": _output(version.n, len(stored), not_catalogued(inputs.code)),
                }
            )
        )
        ports.uow.commit()


def _output(n: int, stored: int, undeclared: Sequence[str]) -> str:
    lines = [f"v{n}: {stored} values", *(f"not catalogued: {path}" for path in undeclared)]
    return "\n".join(lines)
