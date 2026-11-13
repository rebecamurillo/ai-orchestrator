"""Payloads of the run-metrics endpoints (AD-3): the contract is these models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel

from orchestrator.application.metrics.values import MetricValue
from orchestrator.application.use_cases.metrics_read import RunMetrics, VersionView
from orchestrator.domain.entities.metric_results import (
    CalculationState,
    EntryPoint,
    MetricCalculation,
    Origin,
    StoredMetricValue,
)


class OriginOut(BaseModel):
    project_id: UUID
    run_id: UUID
    template_name: str
    template_version: int
    harness: str | None
    harness_na: str | None
    origin_model: str | None
    origin_model_na: str | None
    origin_repository: str | None
    origin_repository_na: str | None
    branch: str | None
    branch_na: str | None
    commit: str | None
    commit_na: str | None
    base_commit: str | None
    base_commit_na: str | None

    @classmethod
    def of(cls, origin: Origin) -> OriginOut:
        return cls(**origin.model_dump())


class MetricValueOut(BaseModel):
    metric_id: str
    method_id: str
    scope_type: str
    scope_key: str
    scope_label: str | None
    role: str | None
    model: str | None
    repository: str | None
    attempt_n: int | None
    source: str | None
    value_num: str | None
    unit: str
    missing: str | None
    partial_n: int | None
    partial_m: int | None
    carried_from: int | None
    origin: OriginOut | None

    @classmethod
    def of(cls, value: StoredMetricValue | MetricValue) -> MetricValueOut:
        figure = value.value_num
        origin = value.origin if isinstance(value, StoredMetricValue) else None
        return cls(
            metric_id=value.metric_id,
            method_id=value.method_id,
            scope_type=value.scope_type,
            scope_key=value.scope_key,
            scope_label=value.scope_label,
            role=value.role,
            model=value.model,
            repository=value.repository,
            attempt_n=value.attempt_n,
            source=value.source,
            value_num=None if figure is None else _decimal(figure),
            unit=value.unit,
            missing=value.missing,
            partial_n=value.partial_n,
            partial_m=value.partial_m,
            carried_from=value.carried_from,
            origin=None if origin is None else OriginOut.of(origin),
        )


def _decimal(figure: Decimal) -> str:
    return format(figure, "f")


class RunMetricsOut(BaseModel):
    run_id: UUID
    version: int | None
    latest: int | None
    values_so_far: bool
    items: list[MetricValueOut]

    @classmethod
    def of(cls, metrics: RunMetrics) -> RunMetricsOut:
        return cls(
            run_id=metrics.run_id,
            version=None if metrics.version is None else metrics.version.n,
            latest=metrics.latest_n,
            values_so_far=metrics.values_so_far,
            items=[MetricValueOut.of(item) for item in metrics.items],
        )


class ResultVersionOut(BaseModel):
    n: int
    calculated_at: datetime
    entry_point: list[EntryPoint]
    methods_changed: list[str]

    @classmethod
    def of(cls, view: VersionView) -> ResultVersionOut:
        return cls(
            n=view.n,
            calculated_at=view.calculated_at,
            entry_point=list(view.entry_point),
            methods_changed=view.methods_changed,
        )


class CalculationOut(BaseModel):
    id: UUID
    run_id: UUID
    target_n: int
    state: CalculationState
    entry_point: list[EntryPoint]
    queued_at: datetime
    started_at: datetime | None
    ended_at: datetime | None
    output: str

    @classmethod
    def of(cls, calculation: MetricCalculation) -> CalculationOut:
        return cls(
            id=calculation.id,
            run_id=calculation.run_id,
            target_n=calculation.target_n,
            state=calculation.state,
            entry_point=list(calculation.entry_point),
            queued_at=calculation.queued_at,
            started_at=calculation.started_at,
            ended_at=calculation.ended_at,
            output=calculation.output,
        )
