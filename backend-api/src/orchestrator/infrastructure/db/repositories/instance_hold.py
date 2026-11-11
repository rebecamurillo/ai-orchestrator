"""The SQLAlchemy adapter for the `InstanceHoldRepository` port (SPEC CAP-4, AD-30).

The locks are table locks. A row lock cannot cover the absent row "create it if absent"
refers to, and under READ COMMITTED a `SELECT … FOR SHARE` does not wait on another
transaction's uncommitted insert. `SHARE` and `SHARE ROW EXCLUSIVE` conflict in both orders,
so a hold placed after a start in flight waits for it and sees its `running` row, and a start
after the hold's lock waits for the hold's commit and sees the hold. Nothing here commits:
the caller's unit of work does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, select, text

from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.infrastructure.db.models.instance_hold import INSTANCE_HOLD_TABLE, InstanceHoldRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

SHARE_LOCK = f"LOCK TABLE {INSTANCE_HOLD_TABLE} IN SHARE MODE"
WRITE_LOCK = f"LOCK TABLE {INSTANCE_HOLD_TABLE} IN SHARE ROW EXCLUSIVE MODE"


def to_entity(row: InstanceHoldRow) -> InstanceHold:
    return InstanceHold(
        id=row.id, held_at=row.held_at, expires_at=row.expires_at, reason=row.reason
    )


class SQLAlchemyInstanceHoldRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self) -> InstanceHold | None:
        return self._select()

    def get_shared(self) -> InstanceHold | None:
        self._session.execute(text(SHARE_LOCK))
        return self._select()

    def get_for_update(self) -> InstanceHold | None:
        self._session.execute(text(WRITE_LOCK))
        return self._select()

    def put(self, hold: InstanceHold) -> None:
        self._session.execute(delete(InstanceHoldRow).where(InstanceHoldRow.id != hold.id))
        self._session.merge(
            InstanceHoldRow(
                id=hold.id,
                held_at=hold.held_at,
                expires_at=hold.expires_at,
                reason=hold.reason,
            )
        )
        self._session.flush()

    def delete_all(self) -> None:
        self._session.execute(delete(InstanceHoldRow))

    def _select(self) -> InstanceHold | None:
        row = self._session.scalars(
            select(InstanceHoldRow).order_by(InstanceHoldRow.held_at.desc()).limit(1)
        ).first()
        return None if row is None else to_entity(row)
