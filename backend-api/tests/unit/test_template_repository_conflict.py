"""The repository's `source` column, `names_with_source`, the unstorable-key guard and the
`IntegrityError` → `Conflict` mapping (story 4, AD-26, D13)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from orchestrator.application.use_cases.templates import TemplatePorts, save_version, seed_shipped
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.errors import Conflict
from orchestrator.infrastructure.db import SQLAlchemyTemplateVersionRepository
from orchestrator.infrastructure.db.models.template import TemplateVersionRow
from orchestrator.infrastructure.db.repositories.templates import to_entity
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

AT = datetime(2026, 11, 6, tzinfo=UTC)
TEXT = "name: story\nversion: 1\nsteps:\n  - id: s\n    uses: git.sync\n    gate: deterministic\n"
BIG = 3_000_000_000


class Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class Session:
    def __init__(self, rows: list[Any] | None = None, flush_error: Exception | None = None) -> None:
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self._rows = rows or []
        self._flush_error = flush_error

    def scalars(self, statement: Any) -> Result:
        self.statements.append(statement)
        return Result(self._rows)

    def get(self, entity: type, key: Any) -> None:
        return None

    def add(self, row: Any) -> None:
        self.added.append(row)

    def flush(self) -> None:
        if self._flush_error is not None:
            raise self._flush_error


def repo(session: Session) -> SQLAlchemyTemplateVersionRepository:
    return SQLAlchemyTemplateVersionRepository(session)  # type: ignore[arg-type]


def a_version(**over: object) -> TemplateVersion:
    fields: dict[str, object] = {"name": "story", "version": 1, "yaml": TEXT, "hash": "h"}
    fields.update(over)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["\ud800", "a\x00b"])
def test_an_unencodable_or_nul_name_matches_nothing_without_a_statement(name: str) -> None:
    session = Session()

    assert repo(session).get(name, 1) is None
    assert repo(session).list_versions(name) == []
    assert session.statements == []


def test_a_version_beyond_int4_matches_nothing_without_a_statement() -> None:
    session = Session()

    assert repo(session).get("story", BIG) is None
    assert session.statements == []


def test_a_lost_race_is_a_conflict_naming_the_pair() -> None:
    session = Session(flush_error=IntegrityError("insert", {}, Exception("duplicate")))

    with pytest.raises(Conflict, match=r"story@1.*concurrent save"):
        repo(session).add_version(a_version(), description=None)


def test_the_fake_raises_the_same_conflict_while_add_keeps_its_value_error() -> None:
    fake = FakeTemplateVersionRepository([a_version()])

    with pytest.raises(Conflict, match=r"story@1"):
        fake.add_version(a_version(), description=None)
    with pytest.raises(ValueError, match=r"story@1"):
        fake.add(a_version())


def test_the_source_is_carried_row_to_entity_and_back() -> None:
    session = Session()
    repo(session).add_version(a_version(source="folder"), description=None)

    (row,) = [r for r in session.added if isinstance(r, TemplateVersionRow)]

    assert row.source == "folder"
    assert to_entity(row).source == "folder"
    assert to_entity(TemplateVersionRow(**{**_values(row), "source": None})).source is None


def _values(row: TemplateVersionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "yaml": row.yaml,
        "hash": row.hash,
        "calls": row.calls,
        "created_at": row.created_at,
    }


@pytest.mark.parametrize("source", ["folder", "shipped"])
def test_names_with_source_selects_the_distinct_names_of_that_source(source: str) -> None:
    session = Session(rows=["a", "b"])

    names = repo(session).names_with_source(source)

    (statement,) = session.statements
    compiled = statement.compile()
    assert names == {"a", "b"}
    assert "template_version.source" in str(compiled)
    assert "DISTINCT" in str(compiled)
    assert list(compiled.params.values()) == [source]


def test_seeding_and_saving_record_where_the_text_came_from() -> None:
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))

    seed_shipped(ports, [("story", TEXT)])
    saved = save_version(ports, "story", TEXT.replace("version: 1", "version: 2"))

    first = templates.get("story", 1)
    assert first is not None
    assert (first.source, saved.source) == ("shipped", "saved")
