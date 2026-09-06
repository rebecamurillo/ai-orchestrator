"""The SQLAlchemy adapter for the `GateRecordRepository` port (AD-8).

Two methods, and the absence of a third is the rule: a gate record is append-only, so this
class has no `update` and no `delete` — nothing to remember, nothing to review. It mirrors
`tests/unit/fakes/runs.py::FakeGateRecordRepository`, whose `list_for_run` is ordered by
`(at, id)`; the id is the tiebreak because two records written in the same transaction share
an instant, and UUIDv7 sorts by creation, so the id is the order they were appended in.

`add` flushes before it returns, for the reason `repositories/runs.py`'s docstring gives:
this row carries a foreign key to `run`, the two are written in one unit of work, and no
`relationship()` exists for the ORM to order the inserts by. Flushing is not committing —
the transaction stays the unit of work's, and a rollback still discards the record.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.infrastructure.db.models.run import GateRecordRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: GateRecordRow) -> GateRecord:
    """A row as the domain entity every layer above works with."""
    return GateRecord(
        id=row.id,
        run_id=row.run_id,
        at=row.at,
        path=row.path,
        event=row.event,
        actor=row.actor,
        text=row.text,
        attempt_n=row.attempt_n,
        payload=dict(row.payload),
    )


def row_values(record: GateRecord) -> dict[str, Any]:
    """Every column of the `gate_record` table, keyed by name."""
    return {
        "id": record.id,
        "run_id": record.run_id,
        "at": record.at,
        "path": record.path,
        "event": record.event,
        "actor": record.actor,
        "text": record.text,
        "attempt_n": record.attempt_n,
        "payload": dict(record.payload),
    }


class SQLAlchemyGateRecordRepository:
    """A Run's gate record, over one open session. Append and read, nothing else."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, record: GateRecord) -> None:
        self._session.add(GateRecordRow(**row_values(record)))
        # emitted now, against the `run` row its adapter already flushed
        self._session.flush()

    def list_for_run(self, run_id: UUID) -> list[GateRecord]:
        rows = self._session.scalars(
            select(GateRecordRow)
            .where(GateRecordRow.run_id == run_id)
            .order_by(GateRecordRow.at, GateRecordRow.id)
        ).all()
        return [to_entity(row) for row in rows]
