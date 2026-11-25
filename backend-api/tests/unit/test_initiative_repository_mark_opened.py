"""`mark_opened` sets `last_opened_at` in one UPDATE that keeps `updated_at` (Operator ruling
2026-11-25, story 6 of epic 7): a view must not fire the column's `onupdate=func.now()`."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.repositories.initiatives import SQLAlchemyInitiativeRepository
from tests.unit.fakes.initiatives import FakeInitiativeRepository
from tests.unit.initiative_fixtures import an_initiative

AT = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)


class RecordingSession:
    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any) -> None:
        self.statements.append(statement)


def compiled(statement: Any) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


def test_one_update_sets_last_opened_at_and_keeps_updated_at() -> None:
    session = RecordingSession()
    initiative_id = new_id()

    SQLAlchemyInitiativeRepository(session).mark_opened(initiative_id, AT)  # type: ignore[arg-type]

    [statement] = session.statements
    sql = compiled(statement)
    assert sql.startswith("UPDATE initiative SET")
    assert "last_opened_at=%(last_opened_at)s" in sql
    assert "updated_at=initiative.updated_at" in sql
    assert "now()" not in sql
    assert "WHERE initiative.id = %(id_1)s" in sql
    params = statement.compile(dialect=postgresql.dialect()).params
    assert params["last_opened_at"] == AT
    assert params["id_1"] == initiative_id
    assert set(params) == {"last_opened_at", "id_1"}


def test_the_fake_moves_only_last_opened_at() -> None:
    initiative = an_initiative()
    fake = FakeInitiativeRepository([initiative])

    fake.mark_opened(initiative.id, AT)

    stored = fake.get(initiative.id)
    assert stored == initiative.model_copy(update={"last_opened_at": AT})
    assert ("mark_opened", initiative.id) in fake.calls


def test_the_fake_refuses_an_unknown_initiative() -> None:
    with pytest.raises(ValueError, match="no initiative"):
        FakeInitiativeRepository().mark_opened(new_id(), AT)
