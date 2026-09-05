"""The `project` table and its repository, asserted without a database (AD-18).

Two halves. The table is read off `Base.metadata` — the same object Alembic compares
against — so its name, its columns, its types, its two unique indexes and its schema are
checked against what the migration creates. The repository is driven over a session double
that records statements instead of executing them, in the shape
`tests/unit/test_db_adapters.py` established, so the entity-to-row mapping and the ordering
of the list query are proved with no Postgres in the room.

What is left for `tests/e2e/test_projects.py` is the claim only a server settles: that the
statements this module records actually run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Boolean, DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.project import EncryptedEnvVar, Project
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.repositories import ProjectRepository
from orchestrator.infrastructure.db import Base, ProjectRow, SQLAlchemyProjectRepository
from orchestrator.infrastructure.db.repositories.projects import env_vars_json, to_entity

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)

TABLE = Base.metadata.tables["project"]

#: The value a stored token stands in for. Named so an assertion about it can fail.
PLAINTEXT = "s3cr3t-abcdefgh"


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "my-website",
        "name": "My Website",
        "context_text": "read this",
        "context_paths": ("docs/a.md",),
        "env_vars_enc": (EncryptedEnvVar(name="TOKEN_A", value_enc="gAAAAA-token"),),
        "log_prompt_content": True,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


def a_row(project: Project) -> ProjectRow:
    return ProjectRow(
        id=project.id,
        slug=project.slug,
        name=project.name,
        context_text=project.context_text,
        context_paths=list(project.context_paths),
        env_vars_enc=env_vars_json(project),
        log_prompt_content=project.log_prompt_content,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


class RecordingResult:
    """What `Session.scalars` returns, with the rows the test put there."""

    def __init__(self, rows: list[ProjectRow]) -> None:
        self._rows = rows

    def first(self) -> ProjectRow | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[ProjectRow]:
        return list(self._rows)


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self, rows: list[ProjectRow] | None = None) -> None:
        self.added: list[ProjectRow] = []
        self.gets: list[tuple[type, Any]] = []
        self.statements: list[Any] = []
        self.rows = rows or []

    def add(self, row: ProjectRow) -> None:
        self.added.append(row)

    def get(self, entity: type, key: Any) -> ProjectRow | None:
        self.gets.append((entity, key))
        return next((row for row in self.rows if row.id == key), None)

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self.rows)


def repository(session: RecordingSession) -> SQLAlchemyProjectRepository:
    return SQLAlchemyProjectRepository(session)  # type: ignore[arg-type]


# ── the table ────────────────────────────────────────────────────────────────


def test_the_model_declares_the_table_the_migration_creates() -> None:
    assert ProjectRow.__tablename__ == "project"
    assert "project" in Base.metadata.tables


def test_the_table_lives_in_the_schema_alembic_manages() -> None:
    assert TABLE.schema in (None, "public")


def test_the_table_carries_exactly_the_columns_the_entity_has() -> None:
    assert set(TABLE.columns.keys()) == {
        "id",
        "slug",
        "name",
        "context_text",
        "context_paths",
        "env_vars_enc",
        "log_prompt_content",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("id", Uuid),
        ("slug", Text),
        ("name", Text),
        ("context_text", Text),
        ("context_paths", JSONB),
        ("env_vars_enc", JSONB),
        ("log_prompt_content", Boolean),
        ("created_at", DateTime),
        ("updated_at", DateTime),
    ],
)
def test_each_column_has_the_type_the_migration_creates(column: str, kind: type) -> None:
    assert isinstance(TABLE.columns[column].type, kind)


def test_the_timestamps_carry_their_zone() -> None:
    """A `timestamp` without a zone would store the server's local time silently."""
    for column in ("created_at", "updated_at"):
        assert TABLE.columns[column].type.timezone is True  # type: ignore[attr-defined]


def test_no_column_is_nullable() -> None:
    """Absent context is an empty string and an empty list, never a null to branch on."""
    for column in TABLE.columns:
        assert column.nullable is False, column.name


def test_the_id_is_the_primary_key() -> None:
    assert [column.name for column in TABLE.primary_key.columns] == ["id"]


def test_name_and_slug_are_uniquely_indexed() -> None:
    """The use-case check produces the message; the index is the guarantee."""
    indexes = {index.name: index for index in TABLE.indexes}

    assert set(indexes) == {"ix_project_name", "ix_project_slug"}
    for index in indexes.values():
        assert index.unique is True


def test_the_index_names_follow_the_convention_a_downgrade_can_reference() -> None:
    assert {index.name for index in TABLE.indexes} == {"ix_project_name", "ix_project_slug"}
    assert TABLE.primary_key.name == "pk_project"


# ── the repository ───────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port() -> None:
    projects: ProjectRepository = repository(RecordingSession())

    assert isinstance(projects, ProjectRepository)


def test_add_maps_every_field_of_the_entity_onto_a_row() -> None:
    session = RecordingSession()
    project = a_project()

    repository(session).add(project)

    (row,) = session.added
    assert (row.id, row.slug, row.name) == (project.id, project.slug, project.name)
    assert row.context_text == "read this"
    assert row.context_paths == ["docs/a.md"]
    assert row.env_vars_enc == [{"name": "TOKEN_A", "value_enc": "gAAAAA-token"}]
    assert row.log_prompt_content is True
    assert (row.created_at, row.updated_at) == (AT, AT)


def test_a_row_maps_back_to_the_entity_it_came_from() -> None:
    project = a_project()

    assert to_entity(a_row(project)) == project


def test_get_reads_the_row_by_primary_key() -> None:
    project = a_project()
    session = RecordingSession([a_row(project)])

    assert repository(session).get(project.id) == project
    assert session.gets == [(ProjectRow, project.id)]


def test_get_answers_none_for_an_id_that_is_not_stored() -> None:
    """Turning a miss into a `NotFound` is a rule, and rules live in `application/`."""
    assert repository(RecordingSession()).get(new_id()) is None


def test_get_by_slug_selects_on_the_uniquely_indexed_column() -> None:
    project = a_project()
    session = RecordingSession([a_row(project)])

    assert repository(session).get_by_slug("my-website") == project

    (statement,) = session.statements
    rendered = str(statement)
    assert "FROM project" in rendered
    assert "project.slug = " in rendered
    assert statement.compile().params == {"slug_1": "my-website"}


def test_get_by_slug_answers_none_for_a_slug_that_is_not_stored() -> None:
    assert repository(RecordingSession()).get_by_slug("nothing") is None


def test_the_list_query_orders_by_name_as_the_fake_does() -> None:
    project = a_project()
    session = RecordingSession([a_row(project)])

    assert repository(session).list() == [project]

    assert "ORDER BY project.name" in str(session.statements[0])


def test_the_empty_list_is_a_list() -> None:
    assert repository(RecordingSession()).list() == []


def test_update_writes_the_editable_fields_back_onto_the_stored_row() -> None:
    project = a_project()
    row = a_row(project)
    session = RecordingSession([row])
    changed = project.model_copy(
        update={
            "name": "Renamed",
            "context_text": "different",
            "context_paths": ("README.md",),
            "env_vars_enc": (EncryptedEnvVar(name="B", value_enc="gAAAAA-other"),),
            "log_prompt_content": False,
            "updated_at": LATER,
        }
    )

    repository(session).update(changed)

    assert row.name == "Renamed"
    assert row.context_text == "different"
    assert row.context_paths == ["README.md"]
    assert row.env_vars_enc == [{"name": "B", "value_enc": "gAAAAA-other"}]
    assert row.log_prompt_content is False
    assert row.updated_at == LATER


def test_update_never_moves_the_identity_of_the_row() -> None:
    """The slug names a directory on disk and `created_at` is history; neither is editable."""
    project = a_project()
    row = a_row(project)
    session = RecordingSession([row])

    repository(session).update(
        project.model_copy(update={"slug": "somewhere-else", "created_at": LATER})
    )

    assert row.slug == "my-website"
    assert row.created_at == AT


def test_update_rebuilds_the_json_columns_rather_than_mutating_them() -> None:
    """SQLAlchemy does not track a mutation inside a JSON value; the write would be lost."""
    project = a_project()
    row = a_row(project)
    before_paths = row.context_paths
    before_vars = row.env_vars_enc
    session = RecordingSession([row])

    repository(session).update(project.model_copy(update={"context_paths": ("x.md",)}))

    assert row.context_paths is not before_paths
    assert row.env_vars_enc is not before_vars


def test_updating_something_that_was_never_added_is_refused_as_the_fake_refuses_it() -> None:
    session = RecordingSession()

    with pytest.raises(ValueError, match="no project"):
        repository(session).update(a_project())


def test_the_json_shape_is_the_one_the_column_documents() -> None:
    project = a_project(
        env_vars_enc=(
            EncryptedEnvVar(name="A", value_enc="one"),
            EncryptedEnvVar(name="B", value_enc="two"),
        )
    )

    assert env_vars_json(project) == [
        {"name": "A", "value_enc": "one"},
        {"name": "B", "value_enc": "two"},
    ]


def test_the_row_holds_the_token_and_never_the_value_it_hides() -> None:
    """The adapter copies what the use case encrypted, and adds nothing of its own.

    The plaintext is named here so the assertion can actually fail: the entity carries the
    token that `PLAINTEXT` encrypts to, and the whole written row — not only the variable
    column — is searched for the value it stands in for.
    """
    session = RecordingSession()
    project = a_project(
        env_vars_enc=(EncryptedEnvVar(name="TOKEN_A", value_enc=f"gAAAAA-{PLAINTEXT}-enc"),)
    )

    repository(session).add(project)

    row = session.added[0]
    written = " ".join(str(getattr(row, column.name)) for column in TABLE.columns)
    assert f"gAAAAA-{PLAINTEXT}-enc" in str(row.env_vars_enc)
    assert written.count(PLAINTEXT) == 1, "the plaintext reached the row outside its token"


def test_the_id_column_round_trips_a_uuid() -> None:
    project = a_project()

    assert isinstance(to_entity(a_row(project)).id, UUID)
