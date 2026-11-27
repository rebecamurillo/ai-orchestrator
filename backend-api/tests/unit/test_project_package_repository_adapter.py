"""The `project_package` table and its adapter, without a database (story 3 of epic 6)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from orchestrator.domain.entities.project_package import (
    GateWords,
    PackageDeclaration,
    ProjectPackage,
)
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.packages import ProjectPackageRepository
from orchestrator.infrastructure.db import (
    Base,
    ProjectPackageRow,
    SQLAlchemyProjectPackageRepository,
)
from orchestrator.infrastructure.db.repositories.packages import to_entity

TWO = 2
AT = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
TABLE = Base.metadata.tables["project_package"]


def a_package(**overrides: object) -> ProjectPackage:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "path": "pkg",
        "ref": "main",
        "sha": "a" * 40,
        "name": "acme",
        "declaration": PackageDeclaration(
            name="acme",
            sequence=(),
            gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
            status_map={"final": "done"},
        ),
        "installed_at": AT,
    }
    fields.update(overrides)
    return ProjectPackage(**fields)  # type: ignore[arg-type]


def a_row(package: ProjectPackage) -> ProjectPackageRow:
    return ProjectPackageRow(
        id=package.id,
        project_id=package.project_id,
        repository_id=package.repository_id,
        path=package.path,
        ref=package.ref,
        sha=package.sha,
        name=package.name,
        declaration=package.declaration.model_dump(mode="json"),
        installed_at=package.installed_at,
    )


class RecordingResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class RecordingSession:
    def __init__(self, rows: list[ProjectPackageRow] | None = None) -> None:
        self.rows = list(rows or [])
        self.added: list[Any] = []
        self.deleted: list[Any] = []
        self.statements: list[Any] = []
        self.flushes = 0

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self.rows)

    def add(self, row: Any) -> None:
        self.added.append(row)
        self.rows.append(row)

    def delete(self, row: Any) -> None:
        self.deleted.append(row)
        self.rows.remove(row)

    def flush(self) -> None:
        self.flushes += 1


def repository(session: RecordingSession) -> SQLAlchemyProjectPackageRepository:
    return SQLAlchemyProjectPackageRepository(session)  # type: ignore[arg-type]


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(repository(RecordingSession()), ProjectPackageRepository)


def test_the_table_columns_types_and_nullability() -> None:
    kinds = {
        "id": Uuid,
        "project_id": Uuid,
        "repository_id": Uuid,
        "path": Text,
        "ref": Text,
        "sha": Text,
        "name": Text,
        "declaration": JSONB,
        "installed_at": DateTime,
    }
    assert set(TABLE.columns.keys()) == set(kinds)
    for name, kind in kinds.items():
        assert isinstance(TABLE.columns[name].type, kind)
        assert TABLE.columns[name].nullable is False
    assert TABLE.columns["installed_at"].type.timezone is True  # type: ignore[attr-defined]


def test_project_id_is_unique_and_both_foreign_keys_exist() -> None:
    assert TABLE.columns["project_id"].unique is True
    targets = {fk.target_fullname for fk in TABLE.foreign_keys}
    assert targets == {"project.id", "repository.id"}
    assert [c.name for c in TABLE.primary_key.columns] == ["id"]


def test_get_reads_the_declaration_back() -> None:
    package = a_package()

    assert repository(RecordingSession([a_row(package)])).get(package.project_id) == package
    assert repository(RecordingSession()).get(new_id()) is None
    assert to_entity(a_row(package)) == package


def test_put_inserts_a_new_row_and_flushes() -> None:
    session = RecordingSession()
    package = a_package()

    repository(session).put(package)

    assert len(session.added) == 1
    assert to_entity(session.added[0]) == package
    assert session.flushes == 1


def test_put_overwrites_the_stored_row_of_the_project() -> None:
    old = a_package()
    session = RecordingSession([a_row(old)])
    newer = a_package(id=new_id(), project_id=old.project_id, sha="b" * 40, name="other", path="x")

    repository(session).put(newer)

    assert session.added == []
    assert to_entity(session.rows[0]) == old.model_copy(
        update={"sha": "b" * 40, "name": "other", "path": "x", "repository_id": newer.repository_id}
    )


def test_delete_removes_the_row_and_a_missing_one_is_a_no_op() -> None:
    package = a_package()
    session = RecordingSession([a_row(package)])

    repository(session).delete(package.project_id)
    repository(session).delete(package.project_id)

    assert len(session.deleted) == 1
    assert session.flushes == 1


def test_list_by_name_filters_and_orders_by_install_time() -> None:
    session = RecordingSession([a_row(a_package()), a_row(a_package())])

    found = repository(session).list_by_name("acme")

    assert len(found) == TWO
    statement = str(session.statements[0])
    assert "project_package.name" in statement
    assert "ORDER BY project_package.installed_at" in statement


@pytest.mark.parametrize("sha", ["a" * 40])
def test_the_row_keeps_the_sha(sha: str) -> None:
    assert a_row(a_package(sha=sha)).sha == sha


class RacingSession(RecordingSession):
    def flush(self) -> None:
        raise IntegrityError("INSERT", {}, Exception("uq_project_package_project_id"))


def test_a_concurrent_first_install_is_a_conflict_not_a_crash() -> None:
    package = a_package()

    with pytest.raises(Conflict, match="concurrent install; nothing stored"):
        repository(RacingSession()).put(package)
