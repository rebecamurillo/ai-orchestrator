"""Ports for calculations and result versions. Versions and values have no update or delete."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.metric_results import (
    CalculationState,
    MetricCalculation,
    ResultVersion,
    StoredMetricValue,
)


@runtime_checkable
class MetricCalculationRepository(Protocol):
    def add(self, calculation: MetricCalculation) -> None: ...

    def get(self, calculation_id: UUID) -> MetricCalculation | None: ...

    def set(self, calculation: MetricCalculation) -> None:
        """Replace state, started_at, ended_at and output of one calculation."""
        ...

    def active_for_run(self, run_id: UUID) -> MetricCalculation | None:
        """The Run's calculation that is queued or running."""
        ...

    def newest_for_n(self, run_id: UUID, n: int) -> MetricCalculation | None: ...

    def list_by_state(self, state: CalculationState) -> list[MetricCalculation]: ...


@runtime_checkable
class ResultVersionRepository(Protocol):
    def add(self, version: ResultVersion, values: Sequence[StoredMetricValue]) -> None: ...

    def next_n(self, run_id: UUID) -> int:
        """The highest stored n plus one; 1 when the Run has no version."""
        ...

    def get(self, run_id: UUID, n: int) -> ResultVersion | None: ...

    def latest(self, run_id: UUID) -> ResultVersion | None: ...

    def list_for_run(self, run_id: UUID) -> list[ResultVersion]:
        """Ordered by n."""
        ...

    def values(self, version_id: UUID) -> list[StoredMetricValue]: ...
