"""The analysis models and adapter: DDL, compression round trip, no update or delete (5.1)."""

from __future__ import annotations

import zlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.analysis import AnalysisRepository
from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.analysis import AnalysisArtifactRow, AnalysisRow
from orchestrator.infrastructure.db.repositories import analysis as module
from orchestrator.infrastructure.db.repositories.analysis import SQLAlchemyAnalysisRepository
from tests.unit.fakes.analysis import FakeAnalysisRepository

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
RUN = UUID(int=5)
CALCULATION = UUID(int=6)


class Session:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = rows or []
        self.added: list[Any] = []
        self.statements: list[str] = []
        self.flushes = 0

    def add(self, row: Any) -> None:
        self.added.append(row)

    def flush(self) -> None:
        self.flushes += 1

    def scalars(self, statement: Any) -> Any:
        self.statements.append(str(statement.compile(dialect=postgresql.dialect())))
        rows = self.rows

        class Scalars:
            def all(self) -> list[Any]:
                return rows

            def first(self) -> Any:
                return rows[0] if rows else None

        return Scalars()


def an_analysis(**over: Any) -> Analysis:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": RUN,
        "calculation_id": CALCULATION,
        "repository_path": ".",
        "base": "m0",
        "head": "h1",
        "toolset": ({"tool": "git", "version": "2"},),
        "toolset_fingerprint": "fp",
        "declaration_hash": "abc",
        "status": "ok",
        "output": "",
        "created_at": NOW,
    }
    return Analysis(**{**fields, **over})


def test_the_tables_and_their_nullable_columns() -> None:
    tables = Base.metadata.tables
    assert {c.name for c in tables["analysis"].columns if c.nullable} == {
        "base",
        "head",
        "declaration_hash",
    }
    assert not [c for c in tables["analysis_artifact"].columns if c.nullable]
    ddl = str(CreateTable(AnalysisRow.__table__).compile(dialect=postgresql.dialect()))  # type: ignore[arg-type]
    assert "status IN ('ok', 'partial', 'failed')" in ddl
    assert "BYTEA" in str(
        CreateTable(AnalysisArtifactRow.__table__).compile(dialect=postgresql.dialect())  # type: ignore[arg-type]
    )


def test_an_analysis_is_inserted_and_reads_back() -> None:
    analysis = an_analysis()
    session = Session()
    SQLAlchemyAnalysisRepository(session).add(analysis)  # type: ignore[arg-type]
    (row,) = session.added
    assert isinstance(row, AnalysisRow)
    assert row.toolset == [{"tool": "git", "version": "2"}]
    assert session.flushes == 1
    back = SQLAlchemyAnalysisRepository(Session([row])).list_for_calculation(CALCULATION)  # type: ignore[arg-type]
    assert back == [analysis]


def test_an_artifact_body_is_compressed_on_write_and_decompressed_on_read() -> None:
    artifact = AnalysisArtifact(
        id=new_id(), analysis_id=new_id(), tool="ruff", media_type="text/plain", body=b"x" * 500
    )
    session = Session()
    SQLAlchemyAnalysisRepository(session).add_artifact(artifact)  # type: ignore[arg-type]
    (row,) = session.added
    assert row.body == zlib.compress(b"x" * 500)
    assert len(row.body) < 500  # noqa: PLR2004
    reader = SQLAlchemyAnalysisRepository(Session([row]))  # type: ignore[arg-type]
    assert reader.artifact(artifact.analysis_id, "ruff") == artifact
    assert SQLAlchemyAnalysisRepository(Session()).artifact(artifact.analysis_id, "x") is None  # type: ignore[arg-type]


def test_no_update_or_delete_anywhere() -> None:
    for kind in (AnalysisRepository, FakeAnalysisRepository, SQLAlchemyAnalysisRepository):
        names = {n for n in dir(kind) if not n.startswith("_")}
        assert not {n for n in names if n.startswith(("update", "delete", "remove", "set"))}
    source = module.__file__
    assert source is not None
    text = open(source).read()
    assert "update(" not in text
    assert "delete(" not in text


def test_the_repositories_satisfy_the_port() -> None:
    assert isinstance(SQLAlchemyAnalysisRepository(Session()), AnalysisRepository)  # type: ignore[arg-type]
    fake = FakeAnalysisRepository()
    assert isinstance(fake, AnalysisRepository)
    analysis = an_analysis()
    fake.add(analysis)
    assert fake.list_for_calculation(CALCULATION) == [analysis]
    assert fake.list_for_calculation(new_id()) == []
