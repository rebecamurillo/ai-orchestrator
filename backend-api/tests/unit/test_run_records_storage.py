"""The run-record models and adapters: columns, constraints, idempotent inserts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.run_records import MADE_BY, RunCommit, RunRepositoryRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.run_records import RunCommitRepository, RunRepositoryRecords
from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.run_records import RunCommitRow, RunRepositoryRow
from orchestrator.infrastructure.db.repositories.run_records import (
    SQLAlchemyRunCommitRepository,
    SQLAlchemyRunRepositoryRecords,
)
from tests.unit.fakes.run_records import FakeRunCommitRepository, FakeRunRepositoryRecords

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)


class Result:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.rowcount = 0

    def scalar_one_or_none(self) -> Any:
        return self.value


class Session:
    def __init__(self, returned: Any = None, rows: list[Any] | None = None) -> None:
        self.returned = returned
        self.rows = rows or []
        self.statements: list[str] = []

    def execute(self, statement: Any) -> Result:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        return Result(self.returned)

    def scalars(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        rows = self.rows

        class Scalars:
            def all(self) -> list[Any]:
                return rows

            def first(self) -> Any:
                return rows[0] if rows else None

        return Scalars()


def a_record() -> RunRepositoryRecord:
    return RunRepositoryRecord(
        id=new_id(),
        run_id=new_id(),
        path="repos/a",
        remote_url="https://h/o/a.git",
        base_branch="main",
        branch="feat/x",
        base_tip="abc",
    )


def test_both_tables_exist_with_nullability_and_unique_names() -> None:
    tables = Base.metadata.tables
    repository, commit = tables["run_repository"], tables["run_commit"]
    nullable = {c.name for c in repository.columns if c.nullable}
    assert nullable == {"head_pushed", "head_local_at_end"}
    assert not any(c.nullable for c in commit.columns)
    names = {c.name for t in (repository, commit) for c in t.constraints}
    assert {"uq_run_repository_run_path", "uq_run_commit_run_path_sha"} <= names
    assert "ck_run_commit_made_by" in names


def test_made_by_holds_the_six_tokens() -> None:
    assert MADE_BY == ("wip", "prepare", "git.commit", "git.merge", "session", "operator_edit")


def test_repository_add_is_on_conflict_do_nothing_and_reports_the_insert() -> None:
    session = Session(returned=new_id())
    assert SQLAlchemyRunRepositoryRecords(session).add(a_record()) is True  # type: ignore[arg-type]
    assert (
        "ON CONFLICT ON CONSTRAINT uq_run_repository_run_path DO NOTHING" in session.statements[0]
    )
    assert SQLAlchemyRunRepositoryRecords(Session()).add(a_record()) is False  # type: ignore[arg-type]


def test_commit_add_is_on_conflict_do_nothing() -> None:
    session = Session()
    commit = RunCommit(id=new_id(), run_id=new_id(), path=".", sha="s", made_by="wip", at=NOW)
    SQLAlchemyRunCommitRepository(session).add(commit)  # type: ignore[arg-type]
    assert (
        "ON CONFLICT ON CONSTRAINT uq_run_commit_run_path_sha DO NOTHING" in session.statements[0]
    )


def test_the_setters_update_by_run_and_path() -> None:
    session = Session()
    records = SQLAlchemyRunRepositoryRecords(session)  # type: ignore[arg-type]
    records.set_head_pushed(new_id(), "repos/a", "abc")
    records.set_head_local_at_end(new_id(), ".", "def")
    assert "UPDATE run_repository SET head_pushed" in session.statements[0]
    assert "UPDATE run_repository SET head_local_at_end" in session.statements[1]


def test_get_and_list_round_trip_rows_into_entities() -> None:
    record = a_record()
    row = RunRepositoryRow(**record.model_dump())
    records = SQLAlchemyRunRepositoryRecords(Session(rows=[row]))  # type: ignore[arg-type]
    assert records.get(record.run_id, "repos/a") == record
    assert records.list_for_run(record.run_id) == [record]
    assert SQLAlchemyRunRepositoryRecords(Session()).get(record.run_id, "x") is None  # type: ignore[arg-type]
    commit = RunCommit(id=new_id(), run_id=new_id(), path=".", sha="s", made_by="wip", at=NOW)
    commits = SQLAlchemyRunCommitRepository(Session(rows=[RunCommitRow(**commit.model_dump())]))  # type: ignore[arg-type]
    assert commits.list_for_run(commit.run_id) == [commit]


def test_the_adapters_and_the_fakes_satisfy_the_ports() -> None:
    records: RunRepositoryRecords = FakeRunRepositoryRecords()
    commits: RunCommitRepository = FakeRunCommitRepository()
    adapters: tuple[RunRepositoryRecords, RunCommitRepository] = (
        SQLAlchemyRunRepositoryRecords(Session()),  # type: ignore[arg-type]
        SQLAlchemyRunCommitRepository(Session()),  # type: ignore[arg-type]
    )
    assert records.list_for_run(new_id()) == [] and commits.list_for_run(new_id()) == []
    assert len(adapters) == 2  # noqa: PLR2004
