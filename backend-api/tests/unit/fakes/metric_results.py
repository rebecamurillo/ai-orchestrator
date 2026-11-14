"""In-memory calculation and result-version repositories (AD-18). The version fake has no
update and no delete, like the port."""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from orchestrator.domain.entities.metric_results import (
    CALCULATION_ACTIVE,
    CalculationState,
    MetricCalculation,
    ResultVersion,
    StoredMetricValue,
)
from orchestrator.domain.ports.metric_results import (
    MetricCalculationRepository,
    ResultVersionRepository,
)


class FakeMetricCalculationRepository:
    def __init__(self) -> None:
        self.rows: list[MetricCalculation] = []

    def add(self, calculation: MetricCalculation) -> None:
        self.rows.append(calculation)

    def get(self, calculation_id: UUID) -> MetricCalculation | None:
        return next((c for c in self.rows if c.id == calculation_id), None)

    def set(self, calculation: MetricCalculation) -> None:
        index = next(i for i, c in enumerate(self.rows) if c.id == calculation.id)
        self.rows[index] = calculation

    def active_for_run(self, run_id: UUID) -> MetricCalculation | None:
        return next(
            (c for c in self.rows if c.run_id == run_id and c.state in CALCULATION_ACTIVE), None
        )

    def newest_for_n(self, run_id: UUID, n: int) -> MetricCalculation | None:
        found = [c for c in self.rows if c.run_id == run_id and c.target_n == n]
        return max(found, key=lambda c: c.queued_at, default=None)

    def list_by_state(self, state: CalculationState) -> list[MetricCalculation]:
        return [c for c in self.rows if c.state == state]


class FakeResultVersionRepository:
    def __init__(self) -> None:
        self.versions: list[ResultVersion] = []
        self.stored: dict[UUID, list[StoredMetricValue]] = {}

    def add(self, version: ResultVersion, values: Sequence[StoredMetricValue]) -> None:
        if any((v.run_id, v.n) == (version.run_id, version.n) for v in self.versions):
            raise ValueError(f"version {version.n} of run {version.run_id} exists")
        self.versions.append(version)
        self.stored[version.id] = list(values)

    def next_n(self, run_id: UUID) -> int:
        return max((v.n for v in self.versions if v.run_id == run_id), default=0) + 1

    def get(self, run_id: UUID, n: int) -> ResultVersion | None:
        return next((v for v in self.versions if (v.run_id, v.n) == (run_id, n)), None)

    def latest(self, run_id: UUID) -> ResultVersion | None:
        return max(
            (v for v in self.versions if v.run_id == run_id), key=lambda v: v.n, default=None
        )

    def list_for_run(self, run_id: UUID) -> list[ResultVersion]:
        return sorted((v for v in self.versions if v.run_id == run_id), key=lambda v: v.n)

    def values(self, version_id: UUID) -> list[StoredMetricValue]:
        return list(self.stored.get(version_id, []))


assert isinstance(FakeMetricCalculationRepository(), MetricCalculationRepository)
assert isinstance(FakeResultVersionRepository(), ResultVersionRepository)
