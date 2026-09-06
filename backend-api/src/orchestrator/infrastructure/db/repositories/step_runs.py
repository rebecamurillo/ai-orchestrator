"""The SQLAlchemy adapter for the `StepRunRepository` port (AD-7).

It mirrors `tests/unit/fakes/runs.py::FakeStepRunRepository`: `list_for_run` is ordered by
`seq`, `first_queued` is the lowest queued `seq`, a miss is `None`, and `update` refuses an
id the table does not hold. The duplicates the fake raises `ValueError` for are refused here
by the two unique indexes on `(run_id, seq)` and `(run_id, path)` instead — the adapter does
not re-check what the database already guarantees.

`add_many` exists because a plan is written in one unit of work: the whole list is added,
never a row at a time, so a plan is either wholly stored or not stored at all. It flushes
before it returns, for the reason `repositories/runs.py`'s docstring gives: these four
tables are one aggregate in one unit of work, nothing declares a `relationship()`, and
without one the ORM will not order the insert of an `attempt` against the `step_run` it
references. Flushing is not committing — the transaction stays the unit of work's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.step_run import StepRun
from orchestrator.infrastructure.db.models.run import StepRunRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: StepRunRow) -> StepRun:
    """A row as the domain entity every layer above works with."""
    return StepRun(
        id=row.id,
        run_id=row.run_id,
        seq=row.seq,
        path=row.path,
        label=row.label,
        kind=row.kind,
        gate=row.gate,
        status=row.status,
        reason=row.reason,
        with_resolved=dict(row.with_resolved),
        retry_count=row.retry_count,
        redispatch_count=row.redispatch_count,
        frame=row.frame,
        story_id=row.story_id,
    )


def row_values(step: StepRun) -> dict[str, Any]:
    """Every column of the `step_run` table, keyed by name."""
    return {
        "id": step.id,
        "run_id": step.run_id,
        "seq": step.seq,
        "path": step.path,
        "label": step.label,
        "kind": step.kind,
        "gate": step.gate,
        "status": step.status,
        "reason": step.reason,
        "with_resolved": dict(step.with_resolved),
        "retry_count": step.retry_count,
        "redispatch_count": step.redispatch_count,
        "frame": step.frame,
        "story_id": step.story_id,
    }


#: What `update` writes back: every column but the primary key.
MUTABLE_COLUMNS: tuple[str, ...] = tuple(
    column.name for column in StepRunRow.__table__.columns if column.name != "id"
)


class SQLAlchemyStepRunRepository:
    """Stored planned rows, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, steps: list[StepRun]) -> None:
        for step in steps:
            self._session.add(StepRunRow(**row_values(step)))
        # emitted now, so an attempt that references one of these rows cannot go first
        self._session.flush()

    def get_by_seq(self, run_id: UUID, seq: int) -> StepRun | None:
        row = self._session.scalars(
            select(StepRunRow).where(StepRunRow.run_id == run_id, StepRunRow.seq == seq)
        ).first()
        return None if row is None else to_entity(row)

    def list_for_run(self, run_id: UUID) -> list[StepRun]:
        rows = self._session.scalars(
            select(StepRunRow).where(StepRunRow.run_id == run_id).order_by(StepRunRow.seq)
        ).all()
        return [to_entity(row) for row in rows]

    def update(self, step: StepRun) -> None:
        row = self._session.get(StepRunRow, step.id)
        if row is None:
            raise ValueError(f"no step run with id {step.id} is stored")
        values = row_values(step)
        for column in MUTABLE_COLUMNS:
            setattr(row, column, values[column])

    def first_queued(self, run_id: UUID) -> StepRun | None:
        row = self._session.scalars(
            select(StepRunRow)
            .where(StepRunRow.run_id == run_id, StepRunRow.status == "queued")
            .order_by(StepRunRow.seq)
        ).first()
        return None if row is None else to_entity(row)
