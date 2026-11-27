"""`SQLAlchemyInitiativeAdvanceRepository.get` and `update`, without Postgres (epic 8 story 1)."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.initiative import InitiativeAdvanceRow
from orchestrator.infrastructure.db.repositories.initiatives import (
    SQLAlchemyInitiativeAdvanceRepository,
)
from tests.unit.fakes.clock import EPOCH


class StubSession:
    def __init__(self, row: Any = None) -> None:
        self.row = row
        self.flushed = 0
        self.gets: list[dict[str, Any]] = []

    def get(self, model: type, key: object, **options: Any) -> Any:
        assert model is InitiativeAdvanceRow
        self.gets.append(options)
        return self.row

    def flush(self) -> None:
        self.flushed += 1


def an_advance() -> InitiativeAdvance:
    return InitiativeAdvance(
        id=new_id(), initiative_id=new_id(), from_run_id=new_id(), round=1, position=2
    )


def a_row(advance: InitiativeAdvance) -> InitiativeAdvanceRow:
    return InitiativeAdvanceRow(
        id=advance.id,
        initiative_id=advance.initiative_id,
        from_run_id=advance.from_run_id,
        round=advance.round,
        position=advance.position,
        blocked_reason=None,
        consumed_at=None,
    )


def test_get_returns_the_entity_or_none() -> None:
    advance = an_advance()

    assert (
        SQLAlchemyInitiativeAdvanceRepository(StubSession(a_row(advance))).get(advance.id)
        == advance
    )  # type: ignore[arg-type]
    assert SQLAlchemyInitiativeAdvanceRepository(StubSession()).get(advance.id) is None  # type: ignore[arg-type]


def test_get_refreshes_a_row_the_session_already_holds() -> None:
    # The locked re-check of `advance_initiative` runs in the session of its unlocked read.
    session = StubSession()

    SQLAlchemyInitiativeAdvanceRepository(session).get(new_id())  # type: ignore[arg-type]

    assert session.gets == [{"populate_existing": True}]


def test_update_sets_the_two_columns_and_flushes() -> None:
    advance = an_advance()
    row = a_row(advance)
    session = StubSession(row)

    SQLAlchemyInitiativeAdvanceRepository(session).update(  # type: ignore[arg-type]
        advance.model_copy(update={"blocked_reason": "why", "consumed_at": EPOCH})
    )

    assert (row.blocked_reason, row.consumed_at) == ("why", EPOCH)
    assert session.flushed == 1


def test_update_of_an_unknown_advance_is_refused() -> None:
    with pytest.raises(ValueError, match="no advance"):
        SQLAlchemyInitiativeAdvanceRepository(StubSession()).update(an_advance())  # type: ignore[arg-type]
