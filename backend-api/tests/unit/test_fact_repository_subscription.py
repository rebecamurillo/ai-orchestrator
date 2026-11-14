"""The fact-set adapter maps `subscription` both ways and groups it by Run (epic 4 story 1)."""

from __future__ import annotations

from typing import Any

from orchestrator.domain.entities.facts import AttemptFacts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.facts import FactSetRow
from orchestrator.infrastructure.db.repositories.facts import (
    SQLAlchemyFactSetRepository,
    _set_entity,
)
from tests.unit.test_fact_repository_adapter import RecordingSession, a_set


class Rows:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows

    def all(self) -> list[Any]:
        return self.rows


class PairSession:
    def __init__(self, pairs: list[tuple[Any, bool | None]]) -> None:
        self.pairs = pairs
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Rows:
        self.statements.append(str(statement))
        return Rows(self.pairs)


def test_the_insert_carries_the_value() -> None:
    session = RecordingSession(returned=new_id())
    SQLAlchemyFactSetRepository(session).add(a_set(subscription=True), AttemptFacts())  # type: ignore[arg-type]
    assert "subscription" in session.statements[0]


def test_the_entity_reads_the_column_back() -> None:
    assert _set_entity(FactSetRow(**a_set(subscription=False).model_dump())).subscription is False
    assert _set_entity(FactSetRow(**a_set(subscription=True).model_dump())).subscription is True
    assert _set_entity(FactSetRow(**a_set().model_dump())).subscription is None


def test_subscriptions_groups_every_set_by_run_in_one_query() -> None:
    a, b = new_id(), new_id()
    session = PairSession([(a, True), (a, None), (b, False)])

    found = SQLAlchemyFactSetRepository(session).subscriptions([a, b, new_id()])  # type: ignore[arg-type]

    assert found == {a: [True, None], b: [False]}
    assert len(session.statements) == 1
    assert "fact_set.subscription" in session.statements[0]
    assert "IN" in session.statements[0]


def test_subscriptions_of_no_runs_reads_nothing() -> None:
    session = PairSession([])
    assert SQLAlchemyFactSetRepository(session).subscriptions([]) == {}  # type: ignore[arg-type]
    assert session.statements == []
