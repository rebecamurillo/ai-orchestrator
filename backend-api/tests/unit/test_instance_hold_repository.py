"""The `instance_hold` adapter over a recording session, the entity and the shared fake (AD-30)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.instance_hold import InstanceHoldRepository
from orchestrator.infrastructure.db.models.instance_hold import InstanceHoldRow
from orchestrator.infrastructure.db.repositories.instance_hold import (
    SQLAlchemyInstanceHoldRepository,
)
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository

NOW = datetime(2026, 11, 11, 9, 0, tzinfo=UTC)


def a_hold(**over: Any) -> InstanceHold:
    fields: dict[str, Any] = {
        "id": new_id(),
        "held_at": NOW,
        "expires_at": NOW + timedelta(minutes=10),
        "reason": "upgrade",
    }
    fields.update(over)
    return InstanceHold(**fields)


class Rows:
    def __init__(self, rows: list[InstanceHoldRow]) -> None:
        self._rows = rows

    def first(self) -> InstanceHoldRow | None:
        return self._rows[0] if self._rows else None


class RecordingSession:
    def __init__(self, rows: list[InstanceHoldRow] | None = None) -> None:
        self.rows = rows or []
        self.order: list[str] = []
        self.statements: list[str] = []
        self.merged: list[InstanceHoldRow] = []

    def execute(self, statement: Any) -> None:
        self.statements.append(str(statement))
        self.order.append("execute")

    def scalars(self, statement: Any) -> Rows:
        self.statements.append(str(statement))
        self.order.append("select")
        return Rows(self.rows)

    def merge(self, row: InstanceHoldRow) -> None:
        self.merged.append(row)
        self.order.append("merge")

    def flush(self) -> None:
        self.order.append("flush")


def repository(session: RecordingSession) -> SQLAlchemyInstanceHoldRepository:
    return SQLAlchemyInstanceHoldRepository(session)  # type: ignore[arg-type]


def a_row(hold: InstanceHold) -> InstanceHoldRow:
    return InstanceHoldRow(
        id=hold.id, held_at=hold.held_at, expires_at=hold.expires_at, reason=hold.reason
    )


def test_the_shared_read_locks_the_table_in_share_mode_before_it_selects() -> None:
    session = RecordingSession()

    assert repository(session).get_shared() is None

    assert session.order == ["execute", "select"]
    assert session.statements[0] == "LOCK TABLE instance_hold IN SHARE MODE"


def test_the_writers_read_locks_in_share_row_exclusive_mode() -> None:
    session = RecordingSession()

    repository(session).get_for_update()

    assert session.statements[0] == "LOCK TABLE instance_hold IN SHARE ROW EXCLUSIVE MODE"
    assert session.order == ["execute", "select"]


def test_the_plain_read_takes_no_lock_and_selects_the_latest_row() -> None:
    hold = a_hold()
    session = RecordingSession([a_row(hold)])

    assert repository(session).get() == hold

    assert session.order == ["select"]
    assert "ORDER BY instance_hold.held_at DESC" in session.statements[0]
    assert "LIMIT" in session.statements[0]


def test_put_deletes_the_other_ids_then_merges_the_row() -> None:
    hold = a_hold()
    session = RecordingSession()

    repository(session).put(hold)

    assert session.order == ["execute", "merge", "flush"]
    assert session.statements[0].startswith("DELETE FROM instance_hold WHERE")
    assert "instance_hold.id !=" in session.statements[0]
    assert (session.merged[0].id, session.merged[0].reason) == (hold.id, "upgrade")
    assert session.merged[0].expires_at == hold.expires_at


def test_delete_all_deletes_every_row() -> None:
    session = RecordingSession()

    repository(session).delete_all()

    assert session.statements == ["DELETE FROM instance_hold"]


def test_the_fake_and_the_adapter_are_the_port() -> None:
    assert isinstance(FakeInstanceHoldRepository(), InstanceHoldRepository)
    assert isinstance(repository(RecordingSession()), InstanceHoldRepository)


def test_the_fake_records_calls_and_holds_one_row() -> None:
    fake = FakeInstanceHoldRepository()
    first, second = a_hold(), a_hold()

    fake.put(first)
    fake.put(second)

    assert fake.get() == second
    assert fake.get_shared() == second
    assert fake.get_for_update() == second
    fake.delete_all()
    assert fake.hold is None
    assert fake.calls == ["put", "put", "get", "get_shared", "get_for_update", "delete_all"]


def test_a_hold_is_active_only_before_its_expiry() -> None:
    hold = a_hold()

    assert hold.active(hold.expires_at - timedelta(seconds=1)) is True
    assert hold.active(hold.expires_at) is False
    assert hold.active(hold.expires_at + timedelta(seconds=1)) is False
