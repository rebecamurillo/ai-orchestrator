"""Reading a Run's metrics: a stored version, the values so far on a live Run, and the state of
a calculation. Writes nothing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from orchestrator.application.metrics.live import MetricsReadPorts, live_values
from orchestrator.application.metrics.values import MetricValue
from orchestrator.domain.entities.metric_results import (
    EntryPoint,
    MetricCalculation,
    ResultVersion,
    StoredMetricValue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.metric_results import (
    MetricCalculationRepository,
    ResultVersionRepository,
)
from orchestrator.domain.statuses import TERMINAL_RUN


@dataclass(frozen=True)
class MetricsQueryPorts:
    read: MetricsReadPorts
    versions: ResultVersionRepository
    calculations: MetricCalculationRepository


@dataclass(frozen=True)
class RunMetrics:
    run_id: UUID
    version: ResultVersion | None
    latest_n: int | None
    values_so_far: bool
    items: list[StoredMetricValue | MetricValue]


@dataclass(frozen=True)
class VersionView:
    n: int
    calculated_at: datetime
    entry_point: tuple[EntryPoint, ...]
    methods_changed: list[str]


def _require_run(ports: MetricsQueryPorts, run_id: UUID) -> Run:
    run = ports.read.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    return run


def run_metrics(ports: MetricsQueryPorts, run_id: UUID, v: int | None) -> RunMetrics:
    run = _require_run(ports, run_id)
    latest = ports.versions.latest(run_id)
    latest_n = None if latest is None else latest.n
    if v is not None:
        version = ports.versions.get(run_id, v)
        if version is None:
            raise NotFound(f"run {run_id} has no version {v}")
    elif run.status not in TERMINAL_RUN:
        items: list[StoredMetricValue | MetricValue] = list(live_values(ports.read, run_id))
        return RunMetrics(run_id, None, latest_n, True, items)
    else:
        version = latest
    if version is None:
        return RunMetrics(run_id, None, None, False, [])
    return RunMetrics(run_id, version, latest_n, False, list(ports.versions.values(version.id)))


def list_versions(ports: MetricsQueryPorts, run_id: UUID) -> list[VersionView]:
    _require_run(ports, run_id)
    views: list[VersionView] = []
    previous: set[str] = set()
    for version in ports.versions.list_for_run(run_id):
        methods = set(version.methods)
        changed = sorted(methods ^ previous) if views else []
        views.append(VersionView(version.n, version.calculated_at, version.entry_point, changed))
        previous = methods
    return views


def calculation_for(ports: MetricsQueryPorts, run_id: UUID, n: int) -> MetricCalculation:
    _require_run(ports, run_id)
    calculation = ports.calculations.newest_for_n(run_id, n)
    if calculation is None:
        raise NotFound(f"run {run_id} has no calculation v{n}")
    return calculation
