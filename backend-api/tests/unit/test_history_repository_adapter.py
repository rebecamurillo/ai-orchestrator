"""The SQLAlchemy adapter behind the `HistoryQuery` port (story 7-5), without a database.

The same two halves `test_run_repository_adapter.py` uses: the statement is driven over a
session double that records instead of connecting, and it is compiled to SQL so the parts
that only the index can honour — the join, the `started_at desc, id desc` order, the keyset
window, the limit — are asserted as text rather than trusted. `tests/e2e/test_history.py`
runs the same query against Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.history import HistoryCursor, HistoryQuery, HistoryQuerySpec
from orchestrator.infrastructure.db import SQLAlchemyHistoryQuery
from orchestrator.infrastructure.db.models.project import ProjectRow
from orchestrator.infrastructure.db.models.run import AttemptRow, RunRow, StepRunRow

AT = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
STEP_SEQ = 2


class RecordingResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return self._rows


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records the statement, it does not run it."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.statements: list[Any] = []
        self._rows = rows or []

    def execute(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self._rows)


def sql(session: RecordingSession) -> str:
    return str(session.statements[-1].compile(compile_kwargs={"literal_binds": False}))


def query(session: RecordingSession) -> SQLAlchemyHistoryQuery:
    return SQLAlchemyHistoryQuery(session)  # type: ignore[arg-type]


def a_spec(**overrides: object) -> HistoryQuerySpec:
    fields: dict[str, object] = {"limit": 50}
    fields.update(overrides)
    return HistoryQuerySpec(**fields)  # type: ignore[arg-type]


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(query(RecordingSession()), HistoryQuery)


def test_the_statement_joins_the_four_tables_the_row_is_read_from() -> None:
    session = RecordingSession()

    query(session).list_attempts(a_spec())

    text = sql(session)
    for table in (
        AttemptRow.__tablename__,
        StepRunRow.__tablename__,
        RunRow.__tablename__,
        ProjectRow.__tablename__,
    ):
        assert table in text


def test_the_statement_orders_newest_first_with_the_id_breaking_a_tie() -> None:
    session = RecordingSession()

    query(session).list_attempts(a_spec())

    text = sql(session).replace("\n", " ")
    assert "ORDER BY" in text
    assert "started_at DESC" in text
    assert text.index("started_at DESC") < text.index("id DESC")


def test_an_attempt_that_never_started_is_excluded_by_the_statement() -> None:
    session = RecordingSession()

    query(session).list_attempts(a_spec())

    assert "started_at IS NOT NULL" in sql(session).replace("\n", " ")


def test_the_limit_reaches_the_statement() -> None:
    session = RecordingSession()

    query(session).list_attempts(a_spec(limit=7))

    assert "LIMIT" in sql(session)


def test_the_cursor_becomes_a_keyset_window_not_an_offset() -> None:
    session = RecordingSession()

    query(session).list_attempts(a_spec(after=HistoryCursor(started_at=AT, attempt_id=new_id())))

    text = sql(session).replace("\n", " ")
    assert "OFFSET" not in text
    assert "<" in text


def test_each_filter_reaches_the_statement() -> None:
    session = RecordingSession()

    query(session).list_attempts(
        a_spec(project_id=new_id(), statuses=("done", "error"), harness="codex")
    )

    text = sql(session).replace("\n", " ")
    assert "project_id" in text
    assert "IN " in text
    assert "harness" in text


def test_a_returned_row_becomes_the_joined_entry_every_reader_works_with() -> None:
    run_id, step_id, attempt_id, project_id = new_id(), new_id(), new_id(), new_id()
    run = RunRow(
        id=run_id,
        project_id=project_id,
        repository_id=new_id(),
        template_name="story",
        template_version=1,
        pinned_versions=[],
        inputs={"base_branch": "main"},
        status="running",
        plan_ref=None,
        plan_refs={},
        engine_ref={},
        budget_usd=Decimal("10.000000"),
        spend_usd=Decimal("0.000000"),
        manual_estimate_h=None,
        re_review_done=False,
        accepted_paths=[],
        worktrees=[],
        compare_urls=[],
        terminal_session=False,
        terminal_clean_polls=0,
        active_seconds=0,
        created_at=AT,
        worktrees_removed=False,
    )
    step = StepRunRow(
        id=step_id,
        run_id=run_id,
        seq=STEP_SEQ,
        path="epics[0].stories[0].build",
        label="build",
        kind="agent",
        gate="deterministic",
        status="done",
        with_resolved={},
        retry_count=0,
        redispatch_count=0,
    )
    attempt = AttemptRow(
        id=attempt_id,
        run_id=run_id,
        step_run_id=step_id,
        n=1,
        status="done",
        started_at=AT,
        engine_ref={},
        cost_provisional=False,
    )
    session = RecordingSession([(attempt, step, run, "acme")])

    entries = query(session).list_attempts(a_spec())

    assert len(entries) == 1
    entry = entries[0]
    assert entry.attempt.id == attempt_id
    assert entry.step.seq == STEP_SEQ
    assert entry.run.id == run_id
    assert entry.project_name == "acme"
