"""The `template`/`template_version` tables and their repository, without a database (AD-18).

Same two halves as `test_project_repository_adapter.py`: the tables are read off
`Base.metadata`, the same object Alembic compares against; the repository is driven over a
session double that records calls instead of executing SQL. `list_versions` and `list`
select a single column and a whole row respectively, so the double is preloaded with
whatever shape a real single-column or whole-row query actually returns rather than always
a list of ORM rows. `callers_of` filters in Python over an unfiltered "select every row",
so that one test genuinely exercises the adapter's own containment check, not a canned
answer standing in for one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.templates import TemplateVersionRepository
from orchestrator.infrastructure.db import Base, SQLAlchemyTemplateVersionRepository
from orchestrator.infrastructure.db.models.template import TemplateRow, TemplateVersionRow
from orchestrator.infrastructure.db.repositories.templates import calls_json, to_entity

AT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)

VERSION_TABLE = Base.metadata.tables["template_version"]
TEMPLATE_TABLE = Base.metadata.tables["template"]


def a_version(**overrides: object) -> TemplateVersion:
    fields: dict[str, object] = {
        "id": new_id(),
        "name": "story",
        "version": 1,
        "yaml": "name: story\nversion: 1\nsteps: []\n",
        "hash": "sha256:abc",
        "calls": (),
        "created_at": AT,
    }
    fields.update(overrides)
    return TemplateVersion(**fields)  # type: ignore[arg-type]


def a_row(version: TemplateVersion) -> TemplateVersionRow:
    return TemplateVersionRow(
        id=version.id,
        name=version.name,
        version=version.version,
        yaml=version.yaml,
        hash=version.hash,
        calls=calls_json(version),
        created_at=version.created_at,
    )


class RecordingResult:
    """What `Session.scalars` returns: one canned answer, whatever shape it holds."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def all(self) -> list[Any]:
        return list(self._rows)


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect.

    `scalars_queue` holds one canned answer per expected call, popped in call order — the
    shape `list()` needs, since it calls `scalars()` twice for two different queries.
    """

    def __init__(
        self,
        template_rows: list[TemplateRow] | None = None,
        scalars_queue: list[list[Any]] | None = None,
    ) -> None:
        self.added: list[Any] = []
        self.gets: list[tuple[type, Any]] = []
        self.statements: list[Any] = []
        self._template_rows = {row.name: row for row in template_rows or []}
        self._scalars_queue = list(scalars_queue or [])

    def add(self, row: Any) -> None:
        self.added.append(row)

    def get(self, entity: type, key: Any) -> Any:
        self.gets.append((entity, key))
        if entity is TemplateRow:
            return self._template_rows.get(key)
        return None

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self._scalars_queue.pop(0))


def repository(session: RecordingSession) -> SQLAlchemyTemplateVersionRepository:
    return SQLAlchemyTemplateVersionRepository(session)  # type: ignore[arg-type]


# --- the tables ----------------------------------------------------------------------------


def test_the_models_declare_the_tables_the_migration_creates() -> None:
    assert TemplateRow.__tablename__ == "template"
    assert TemplateVersionRow.__tablename__ == "template_version"
    assert {"template", "template_version"} <= set(Base.metadata.tables)


def test_the_version_table_carries_exactly_the_columns_the_entity_needs() -> None:
    assert set(VERSION_TABLE.columns.keys()) == {
        "id",
        "name",
        "version",
        "yaml",
        "hash",
        "calls",
        "created_at",
    }


def test_the_template_table_carries_name_description_and_created_at() -> None:
    assert set(TEMPLATE_TABLE.columns.keys()) == {"name", "description", "created_at"}


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("id", Uuid),
        ("name", Text),
        ("version", Integer),
        ("yaml", Text),
        ("hash", Text),
        ("calls", JSONB),
        ("created_at", DateTime),
    ],
)
def test_each_version_column_has_the_type_the_migration_creates(column: str, kind: type) -> None:
    assert isinstance(VERSION_TABLE.columns[column].type, kind)


def test_the_version_created_at_carries_its_zone() -> None:
    assert VERSION_TABLE.columns["created_at"].type.timezone is True  # type: ignore[attr-defined]


def test_the_description_column_alone_may_be_null() -> None:
    assert TEMPLATE_TABLE.columns["description"].nullable is True
    for column in TEMPLATE_TABLE.columns:
        if column.name != "description":
            assert column.nullable is False, column.name
    for column in VERSION_TABLE.columns:
        assert column.nullable is False, column.name


def test_the_version_table_is_keyed_by_id_and_indexed_on_name_and_version() -> None:
    assert [column.name for column in VERSION_TABLE.primary_key.columns] == ["id"]
    indexes = {index.name: index for index in VERSION_TABLE.indexes}
    assert set(indexes) == {"ix_template_version_name_version"}
    index = indexes["ix_template_version_name_version"]
    assert index.unique is True
    assert {column.name for column in index.columns} == {"name", "version"}


def test_the_version_table_has_a_foreign_key_to_the_template_table() -> None:
    (fk,) = VERSION_TABLE.foreign_keys
    assert fk.column.table.name == "template"


def test_the_template_table_is_keyed_by_name() -> None:
    assert [column.name for column in TEMPLATE_TABLE.primary_key.columns] == ["name"]


# --- to_entity / calls_json ------------------------------------------------------------------


def test_a_row_maps_back_to_the_entity_it_came_from() -> None:
    version = a_version(calls=(TemplateRef(name="epic", version=2),))

    assert to_entity(a_row(version)) == version


def test_calls_json_is_the_jsonb_shape_the_column_holds() -> None:
    version = a_version(calls=(TemplateRef(name="epic", version=2),))

    assert calls_json(version) == [{"name": "epic", "version": 2}]


def test_calls_json_is_empty_for_no_calls() -> None:
    assert calls_json(a_version()) == []


# --- the repository ---------------------------------------------------------------------------


def test_the_adapter_satisfies_the_port() -> None:
    templates: TemplateVersionRepository = repository(RecordingSession(scalars_queue=[[]]))

    assert isinstance(templates, TemplateVersionRepository)


def test_get_reads_the_row_by_name_and_version() -> None:
    version = a_version()
    session = RecordingSession(scalars_queue=[[a_row(version)]])

    assert repository(session).get("story", 1) == version
    rendered = str(session.statements[0])
    assert "template_version.name" in rendered
    assert "template_version.version" in rendered


def test_get_answers_none_for_a_pair_that_is_not_stored() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert repository(session).get("story", 1) is None


def test_add_version_inserts_the_template_row_the_first_time() -> None:
    session = RecordingSession()
    version = a_version()

    repository(session).add_version(version, description="the story loop")

    template_row, version_row = session.added
    assert isinstance(template_row, TemplateRow)
    assert (template_row.name, template_row.description) == ("story", "the story loop")
    assert isinstance(version_row, TemplateVersionRow)
    assert (version_row.id, version_row.name, version_row.version) == (
        version.id,
        "story",
        1,
    )
    assert version_row.calls == []


def test_add_version_updates_the_description_when_the_name_already_has_a_row() -> None:
    existing = TemplateRow(name="story", description="old text", created_at=AT)
    session = RecordingSession(template_rows=[existing])

    repository(session).add_version(a_version(version=2), description="new text")

    # no new TemplateRow was added, only the version row
    assert len(session.added) == 1
    assert isinstance(session.added[0], TemplateVersionRow)
    assert existing.description == "new text"


def test_list_versions_is_sorted_ascending_however_the_rows_arrive() -> None:
    session = RecordingSession(scalars_queue=[[2, 1, 3]])

    assert repository(session).list_versions("story") == [1, 2, 3]
    assert "template_version.name" in str(session.statements[0])


def test_list_versions_is_empty_for_an_unknown_name() -> None:
    session = RecordingSession(scalars_queue=[[]])

    assert repository(session).list_versions("nothing") == []


def test_list_groups_versions_by_name_with_the_templates_description() -> None:
    rows = [
        a_row(a_version(name="story", version=1)),
        a_row(a_version(name="story", version=2)),
        a_row(a_version(name="epic", version=1)),
    ]
    templates = [
        TemplateRow(name="story", description="story text", created_at=AT),
        TemplateRow(name="epic", description=None, created_at=AT),
    ]
    session = RecordingSession(scalars_queue=[rows, templates])
    story_latest_version = 2

    summaries = {summary.name: summary for summary in repository(session).list()}

    assert summaries["story"].versions == (1, 2)
    assert summaries["story"].latest_version == story_latest_version
    assert summaries["story"].description == "story text"
    assert summaries["epic"].description is None


def test_list_is_empty_when_nothing_is_stored() -> None:
    session = RecordingSession(scalars_queue=[[], []])

    assert repository(session).list() == []


def test_callers_of_filters_in_python_over_every_stored_row() -> None:
    rows = [
        a_row(a_version(name="story", version=1)),
        a_row(a_version(name="epic", version=1, calls=(TemplateRef(name="story", version=1),))),
        a_row(
            a_version(name="initiative", version=1, calls=(TemplateRef(name="epic", version=1),))
        ),
    ]
    session = RecordingSession(scalars_queue=[rows])

    assert repository(session).callers_of("story", 1) == [TemplateRef(name="epic", version=1)]


def test_callers_of_is_empty_when_nothing_calls_it() -> None:
    rows = [a_row(a_version(name="story", version=1))]
    session = RecordingSession(scalars_queue=[rows])

    assert repository(session).callers_of("story", 1) == []
