"""SQLAlchemy adapters for calculations and result versions.

`ResultVersion`s and their values are only ever inserted: this module has no update or delete
for them. A calculation's `set` replaces state, started_at, ended_at and output.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import func, select, update

from orchestrator.domain.entities.metric_results import (
    CALCULATION_ACTIVE,
    CalculationState,
    MetricCalculation,
    Origin,
    ResultVersion,
    StoredMetricValue,
)
from orchestrator.infrastructure.db.models.metric_results import (
    MetricCalculationRow,
    MetricValueRow,
    ResultVersionRow,
)

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

ORIGIN_FIELDS = tuple(Origin.model_fields)


def _calculation(row: MetricCalculationRow) -> MetricCalculation:
    return MetricCalculation(
        id=row.id,
        run_id=row.run_id,
        target_n=row.target_n,
        state=row.state,  # type: ignore[arg-type]
        entry_point=tuple(row.entry_point),  # type: ignore[arg-type]
        queued_at=row.queued_at,
        started_at=row.started_at,
        ended_at=row.ended_at,
        output=row.output,
    )


def _version(row: ResultVersionRow) -> ResultVersion:
    return ResultVersion(
        id=row.id,
        run_id=row.run_id,
        n=row.n,
        calculated_at=row.calculated_at,
        entry_point=tuple(row.entry_point),  # type: ignore[arg-type]
        methods=tuple(row.methods),
        fact_set_ids=tuple(UUID(item) for item in row.fact_set_ids),
        toolset_fingerprint=row.toolset_fingerprint,
    )


def _value_row(value: StoredMetricValue) -> MetricValueRow:
    figures = value.model_dump(exclude={"origin"})
    return MetricValueRow(**figures, **value.origin.model_dump())


def _value(row: MetricValueRow) -> StoredMetricValue:
    figures = {
        name: getattr(row, name) for name in StoredMetricValue.model_fields if name != "origin"
    }
    return StoredMetricValue(
        **figures, origin=Origin(**{n: getattr(row, n) for n in ORIGIN_FIELDS})
    )


class SQLAlchemyMetricCalculationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, calculation: MetricCalculation) -> None:
        values = calculation.model_dump()
        values["entry_point"] = list(calculation.entry_point)
        self._session.add(MetricCalculationRow(**values))
        self._session.flush()

    def get(self, calculation_id: UUID) -> MetricCalculation | None:
        row = self._session.get(MetricCalculationRow, calculation_id, populate_existing=True)
        return _calculation(row) if row is not None else None

    def set(self, calculation: MetricCalculation) -> None:
        self._session.execute(
            update(MetricCalculationRow)
            .where(MetricCalculationRow.id == calculation.id)
            .values(
                state=calculation.state,
                started_at=calculation.started_at,
                ended_at=calculation.ended_at,
                output=calculation.output,
            )
        )

    def active_for_run(self, run_id: UUID) -> MetricCalculation | None:
        row = self._session.scalars(
            select(MetricCalculationRow)
            .where(
                MetricCalculationRow.run_id == run_id,
                MetricCalculationRow.state.in_(sorted(CALCULATION_ACTIVE)),
            )
            .order_by(MetricCalculationRow.queued_at.desc())
        ).first()
        return _calculation(row) if row is not None else None

    def newest_for_n(self, run_id: UUID, n: int) -> MetricCalculation | None:
        row = self._session.scalars(
            select(MetricCalculationRow)
            .where(MetricCalculationRow.run_id == run_id, MetricCalculationRow.target_n == n)
            .order_by(MetricCalculationRow.queued_at.desc())
        ).first()
        return _calculation(row) if row is not None else None

    def list_by_state(self, state: CalculationState) -> list[MetricCalculation]:
        rows = self._session.scalars(
            select(MetricCalculationRow)
            .where(MetricCalculationRow.state == state)
            .order_by(MetricCalculationRow.queued_at)
        ).all()
        return [_calculation(row) for row in rows]


class SQLAlchemyResultVersionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, version: ResultVersion, values: Sequence[StoredMetricValue]) -> None:
        dumped = version.model_dump(mode="json")
        self._session.add(
            ResultVersionRow(
                **{
                    **version.model_dump(),
                    **{
                        "entry_point": dumped["entry_point"],
                        "fact_set_ids": dumped["fact_set_ids"],
                        "methods": dumped["methods"],
                    },
                }
            )
        )
        self._session.flush()
        self._session.add_all([_value_row(value) for value in values])
        self._session.flush()

    def next_n(self, run_id: UUID) -> int:
        highest = self._session.scalar(
            select(func.max(ResultVersionRow.n)).where(ResultVersionRow.run_id == run_id)
        )
        return (highest or 0) + 1

    def get(self, run_id: UUID, n: int) -> ResultVersion | None:
        row = self._session.scalars(
            select(ResultVersionRow).where(
                ResultVersionRow.run_id == run_id, ResultVersionRow.n == n
            )
        ).first()
        return _version(row) if row is not None else None

    def latest(self, run_id: UUID) -> ResultVersion | None:
        row = self._session.scalars(
            select(ResultVersionRow)
            .where(ResultVersionRow.run_id == run_id)
            .order_by(ResultVersionRow.n.desc())
        ).first()
        return _version(row) if row is not None else None

    def list_for_run(self, run_id: UUID) -> list[ResultVersion]:
        rows = self._session.scalars(
            select(ResultVersionRow)
            .where(ResultVersionRow.run_id == run_id)
            .order_by(ResultVersionRow.n)
        ).all()
        return [_version(row) for row in rows]

    def values(self, version_id: UUID) -> list[StoredMetricValue]:
        rows = self._session.scalars(
            select(MetricValueRow)
            .where(MetricValueRow.version_id == version_id)
            .order_by(MetricValueRow.metric_id, MetricValueRow.scope_type, MetricValueRow.scope_key)
        ).all()
        return [_value(row) for row in rows]
