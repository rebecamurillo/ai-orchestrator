"""The fact adapters over a recording session: append-only, idempotent on the unique triple."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.facts import (
    ActivityFact,
    AttemptFacts,
    EventFact,
    FactSet,
    GapFact,
    GatewayRead,
    RequestFact,
    UsageFact,
)
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.db.models.facts import (
    ActivityFactRow,
    EventFactRow,
    FactSetRow,
    GapFactRow,
    GatewayReadRow,
    RequestFactRow,
    UsageFactRow,
)
from orchestrator.infrastructure.db.repositories.facts import (
    SQLAlchemyFactSetRepository,
    SQLAlchemyGatewayReadRepository,
)

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)

FACTS = AttemptFacts(
    usage=(UsageFact(source="harness", model="m", usage_class="money", usd=Decimal("0.5")),),
    requests=(
        RequestFact(
            message_id="m1",
            model="m",
            conversation="main",
            input_uncached=1,
            cache_read=2,
            cache_write_5m=3,
            cache_write_1h=4,
            output=5,
        ),
    ),
    activity=(
        ActivityFact(
            conversation="main",
            tool="Bash",
            calls=1,
            errors=0,
            files_read=0,
            files_edited=0,
            test_runs=1,
            messages=2,
        ),
    ),
    gaps=(GapFact(conversation="main", messages=2, first_at=NOW, last_at=NOW, gaps_s=(4, 5)),),
    events=(EventFact(at=NOW, conversation="main", kind="test_run", command="pytest"),),
)


def a_set(**over: Any) -> FactSet:
    fields: dict[str, Any] = {
        "id": new_id(),
        "attempt_id": new_id(),
        "run_id": new_id(),
        "extractor": "fake",
        "extractor_version": 1,
        "read_at": NOW,
        "status": "ok",
    }
    fields.update(over)
    return FactSet(**fields)


class Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value

    def all(self) -> list[Any]:
        return self.value if isinstance(self.value, list) else []


class RecordingSession:
    def __init__(self, returned: Any = None, selected: dict[type, list[Any]] | None = None) -> None:
        self.returned = returned
        self.selected = selected or {}
        self.statements: list[str] = []
        self.added: list[Any] = []
        self.header: Any = None
        self.flushed_at: int | None = None

    def execute(self, statement: Any) -> Result:
        self.statements.append(str(statement.compile(dialect=_postgres())))
        return Result(self.returned)

    def add(self, row: Any) -> None:
        self.added.append(row)

    def add_all(self, rows: Any) -> None:
        self.added.extend(rows)

    def flush(self) -> None:
        self.flushed_at = len(self.added)

    def get(self, _model: Any, _id: Any) -> Any:
        return self.header

    def scalars(self, statement: Any) -> Result:
        text = str(statement)
        self.statements.append(text)
        for model, rows in self.selected.items():
            if model.__tablename__ in text.split("FROM", 1)[-1].split()[0:1]:
                return Result(rows)
        return Result([])


def _postgres() -> Any:
    return postgresql.dialect()


def test_add_emits_an_insert_that_does_nothing_on_conflict_and_keeps_child_rows() -> None:
    parent = new_id()
    session = RecordingSession(returned=parent)
    stored = SQLAlchemyFactSetRepository(session).add(a_set(), FACTS)  # type: ignore[arg-type]

    assert stored is True
    assert (
        "ON CONFLICT ON CONSTRAINT uq_fact_set_attempt_extractor_version DO NOTHING"
        in (session.statements[0])
    )
    kinds = {type(r) for r in session.added}
    assert kinds == {UsageFactRow, RequestFactRow, ActivityFactRow, GapFactRow, EventFactRow}
    assert all(r.fact_set_id == parent for r in session.added)
    assert len({r.id for r in session.added}) == len(session.added)
    [gap] = [r for r in session.added if isinstance(r, GapFactRow)]
    assert gap.gaps_s == [4, 5]
    [usage] = [r for r in session.added if isinstance(r, UsageFactRow)]
    assert usage.usage_class == "money" and usage.gateway_read_id is None


def test_a_conflict_returns_false_and_adds_nothing() -> None:
    session = RecordingSession(returned=None)
    assert SQLAlchemyFactSetRepository(session).add(a_set(), FACTS) is False  # type: ignore[arg-type]
    assert session.added == []


def test_a_gateway_read_carries_its_usage_rows_under_the_read_only() -> None:
    session = RecordingSession()
    read = GatewayRead(
        id=new_id(),
        attempt_id=new_id(),
        run_id=new_id(),
        read_at=NOW,
        trigger="attempt_end",
        provisional=False,
        usd=Decimal("1"),
    )
    SQLAlchemyGatewayReadRepository(session).add(read, FACTS.usage)  # type: ignore[arg-type]

    [head, child] = session.added
    assert isinstance(head, GatewayReadRow) and head.capped is False
    assert isinstance(child, UsageFactRow)
    assert (child.gateway_read_id, child.fact_set_id) == (read.id, None)
    assert session.flushed_at == 1


def test_neither_adapter_can_update_or_delete() -> None:
    for adapter in (SQLAlchemyFactSetRepository, SQLAlchemyGatewayReadRepository):
        public = {n for n in dir(adapter) if not n.startswith("_")}
        assert not {n for n in public if "update" in n or "delete" in n or "remove" in n}


def test_a_set_reads_back_as_the_entity() -> None:
    attempt_id = new_id()
    row = FactSetRow(
        id=new_id(),
        attempt_id=attempt_id,
        run_id=new_id(),
        extractor="fake",
        extractor_version=1,
        read_at=NOW,
        status="partial",
        reason="r",
    )
    sets = SQLAlchemyFactSetRepository(RecordingSession(selected={FactSetRow: [row]}))  # type: ignore[arg-type]
    [entity] = sets.list_for_attempt(attempt_id)
    assert (entity.id, entity.status, entity.reason) == (row.id, "partial", "r")


def test_the_rows_of_a_set_round_trip() -> None:
    set_id = new_id()
    session = RecordingSession(
        selected={
            UsageFactRow: [
                UsageFactRow(
                    id=new_id(),
                    fact_set_id=set_id,
                    gateway_read_id=None,
                    source="harness",
                    model="m",
                    conversation=None,
                    subagent_type=None,
                    usage_class="money",
                    tokens=None,
                    usd=Decimal("0.5"),
                    calls=None,
                )
            ],
            GapFactRow: [
                GapFactRow(
                    id=new_id(),
                    fact_set_id=set_id,
                    conversation="main",
                    messages=2,
                    first_at=NOW,
                    last_at=NOW,
                    gaps_s=[4, 5],
                )
            ],
        }
    )
    session.header = FactSetRow(status="partial", reason="half")
    rows = SQLAlchemyFactSetRepository(session).rows(set_id)  # type: ignore[arg-type]
    assert rows.status == "partial" and rows.reason == "half"
    assert rows.usage[0].usd == Decimal("0.5")
    assert rows.gaps[0].gaps_s == (4, 5)


@pytest.mark.parametrize("header", [None, FactSetRow(status="ok", reason=None)])
def test_a_set_with_no_header_or_an_ok_one_reads_as_ok(header: Any) -> None:
    session = RecordingSession()
    session.header = header
    rows = SQLAlchemyFactSetRepository(session).rows(new_id())  # type: ignore[arg-type]
    assert rows == AttemptFacts()


def test_unrecorded_attempts_asks_for_ended_harness_attempts_without_a_set() -> None:
    session = RecordingSession()
    SQLAlchemyFactSetRepository(session).unrecorded_attempts(7)  # type: ignore[arg-type]
    text = session.statements[0]
    assert "ended_at IS NOT NULL" in text
    assert "NOT (EXISTS" in text and "fact_set" in text
    assert "ORDER BY attempt.ended_at" in text and "LIMIT" in text


def test_gateway_reads_come_back_newest_first() -> None:
    attempt_id = new_id()
    row = GatewayReadRow(
        id=new_id(),
        attempt_id=attempt_id,
        run_id=new_id(),
        read_at=NOW,
        trigger="run_end",
        rows=None,
        calls=None,
        provisional=True,
        capped=False,
        usd=Decimal("2"),
        prompt=None,
        completion=None,
    )
    session = RecordingSession(selected={GatewayReadRow: [row]})
    [read] = SQLAlchemyGatewayReadRepository(session).list_for_attempt(attempt_id)  # type: ignore[arg-type]
    assert read.trigger == "run_end" and read.usd == Decimal("2")
    assert "ORDER BY gateway_read.read_at DESC" in session.statements[0]
