"""The `repository` table and its repository adapter, asserted without a database (AD-18).

Mirrors `tests/unit/test_project_repository_adapter.py`: the table is read off
`Base.metadata` — the same object Alembic compares against — and the adapter is driven over
a session double that records statements instead of executing them. What is left for
`tests/e2e/test_repositories.py` is the claim only a server settles: that the statements
this module records actually run.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.repository import SUGGESTED_TEST_GLOBS, CloneCheck, Repository
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.repositories import RepositoryRepository
from orchestrator.infrastructure.db import Base, RepositoryRow, SQLAlchemyRepositoryRepository
from orchestrator.infrastructure.db.repositories.repository import clone_check_json, to_entity

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)

TABLE = Base.metadata.tables["repository"]


def a_repository(**overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "slug": "my-repo",
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
        "install_command": "npm ci",
        "quality_gate_command": "make lint test",
        "unit_test_command": "npm test",
        "test_globs": SUGGESTED_TEST_GLOBS,
        "package_manager": "npm",
        "clone_check": CloneCheck.pending(),
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


def a_row(repository: Repository) -> RepositoryRow:
    return RepositoryRow(
        id=repository.id,
        project_id=repository.project_id,
        slug=repository.slug,
        url=repository.url,
        default_branch=repository.default_branch,
        install_command=repository.install_command,
        quality_gate_command=repository.quality_gate_command,
        unit_test_command=repository.unit_test_command,
        test_globs=list(repository.test_globs),
        package_manager=repository.package_manager,
        clone_check=clone_check_json(repository.clone_check),
        created_at=repository.created_at,
        updated_at=repository.updated_at,
    )


class RecordingResult:
    """What `Session.scalars` returns, with the rows the test put there."""

    def __init__(self, rows: list[RepositoryRow]) -> None:
        self._rows = rows

    def first(self) -> RepositoryRow | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[RepositoryRow]:
        return list(self._rows)


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self, rows: list[RepositoryRow] | None = None) -> None:
        self.added: list[RepositoryRow] = []
        self.gets: list[tuple[type, Any]] = []
        self.statements: list[Any] = []
        self.rows = rows or []

    def add(self, row: RepositoryRow) -> None:
        self.added.append(row)

    def get(self, entity: type, key: Any) -> RepositoryRow | None:
        self.gets.append((entity, key))
        return next((row for row in self.rows if row.id == key), None)

    def scalars(self, statement: Any) -> RecordingResult:
        self.statements.append(statement)
        return RecordingResult(self.rows)


def repository_adapter(session: RecordingSession) -> SQLAlchemyRepositoryRepository:
    return SQLAlchemyRepositoryRepository(session)  # type: ignore[arg-type]


# ── the table ────────────────────────────────────────────────────────────────


def test_the_model_declares_the_table_the_migration_creates() -> None:
    assert RepositoryRow.__tablename__ == "repository"
    assert "repository" in Base.metadata.tables


def test_the_table_lives_in_the_schema_alembic_manages() -> None:
    assert TABLE.schema in (None, "public")


def test_the_table_carries_exactly_the_columns_the_entity_has() -> None:
    assert set(TABLE.columns.keys()) == {
        "id",
        "project_id",
        "slug",
        "url",
        "default_branch",
        "install_command",
        "quality_gate_command",
        "unit_test_command",
        "test_globs",
        "package_manager",
        "clone_check",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("id", Uuid),
        ("project_id", Uuid),
        ("slug", Text),
        ("url", Text),
        ("default_branch", Text),
        ("install_command", Text),
        ("quality_gate_command", Text),
        ("unit_test_command", Text),
        ("test_globs", JSONB),
        ("package_manager", Text),
        ("clone_check", JSONB),
        ("created_at", DateTime),
        ("updated_at", DateTime),
    ],
)
def test_each_column_has_the_type_the_migration_creates(column: str, kind: type) -> None:
    assert isinstance(TABLE.columns[column].type, kind)


def test_the_timestamps_carry_their_zone() -> None:
    for column in ("created_at", "updated_at"):
        assert TABLE.columns[column].type.timezone is True  # type: ignore[attr-defined]


def test_no_column_is_nullable() -> None:
    for column in TABLE.columns:
        assert column.nullable is False, column.name


def test_the_id_is_the_primary_key() -> None:
    assert [column.name for column in TABLE.primary_key.columns] == ["id"]


def test_project_id_carries_a_foreign_key_to_project() -> None:
    (fk,) = TABLE.columns["project_id"].foreign_keys
    assert fk.target_fullname == "project.id"


def test_the_project_id_and_url_pair_is_uniquely_indexed() -> None:
    """The use-case check produces the message; the index is the guarantee."""
    indexes = {index.name: index for index in TABLE.indexes}

    assert "ix_repository_project_id_url" in indexes
    index = indexes["ix_repository_project_id_url"]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["project_id", "url"]


def test_the_project_id_and_slug_pair_is_uniquely_indexed() -> None:
    """`_free_repo_slug` reads-then-writes; the index is what a concurrent create cannot
    slip past — the same race class the url index already guards."""
    indexes = {index.name: index for index in TABLE.indexes}

    assert "ix_repository_project_id_slug" in indexes
    index = indexes["ix_repository_project_id_slug"]
    assert index.unique is True
    assert [column.name for column in index.columns] == ["project_id", "slug"]


def test_the_constraint_names_follow_the_convention_a_downgrade_can_reference() -> None:
    assert TABLE.primary_key.name == "pk_repository"


# ── the adapter ──────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port() -> None:
    repositories: RepositoryRepository = repository_adapter(RecordingSession())

    assert isinstance(repositories, RepositoryRepository)


def test_add_maps_every_field_of_the_entity_onto_a_row() -> None:
    session = RecordingSession()
    repository = a_repository()

    repository_adapter(session).add(repository)

    (row,) = session.added
    assert (row.id, row.project_id, row.slug, row.url) == (
        repository.id,
        repository.project_id,
        repository.slug,
        repository.url,
    )
    assert row.default_branch == "main"
    assert row.install_command == "npm ci"
    assert row.quality_gate_command == "make lint test"
    assert row.unit_test_command == "npm test"
    assert row.test_globs == list(SUGGESTED_TEST_GLOBS)
    assert row.package_manager == "npm"
    assert row.clone_check == {
        "status": "pending",
        "at": None,
        "output": "",
        "bmad_version": None,
    }
    assert (row.created_at, row.updated_at) == (AT, AT)


def test_a_row_maps_back_to_the_entity_it_came_from() -> None:
    repository = a_repository()

    assert to_entity(a_row(repository)) == repository


def test_get_reads_the_row_by_primary_key() -> None:
    repository = a_repository()
    session = RecordingSession([a_row(repository)])

    assert repository_adapter(session).get(repository.id) == repository
    assert session.gets == [(RepositoryRow, repository.id)]


def test_get_answers_none_for_an_id_that_is_not_stored() -> None:
    assert repository_adapter(RecordingSession()).get(new_id()) is None


def test_list_by_project_orders_by_created_at_and_filters_on_project_id() -> None:
    repository = a_repository()
    session = RecordingSession([a_row(repository)])

    result = repository_adapter(session).list_by_project(repository.project_id)

    assert result == [repository]
    (statement,) = session.statements
    rendered = str(statement)
    assert "FROM repository" in rendered
    assert "repository.project_id" in rendered
    assert "ORDER BY repository.created_at, repository.id" in rendered
    assert statement.compile().params == {"project_id_1": repository.project_id}


def test_the_empty_list_is_a_list() -> None:
    assert repository_adapter(RecordingSession()).list_by_project(new_id()) == []


def test_update_writes_the_editable_fields_back_onto_the_stored_row() -> None:
    repository = a_repository()
    row = a_row(repository)
    session = RecordingSession([row])
    changed = repository.model_copy(
        update={
            "url": "https://x/renamed.git",
            "default_branch": "develop",
            "install_command": "pnpm i",
            "quality_gate_command": "pnpm lint",
            "unit_test_command": "pnpm test",
            "package_manager": "pnpm",
            "test_globs": (*SUGGESTED_TEST_GLOBS, "e2e/**"),
            "clone_check": CloneCheck(status="ok", at=LATER, output="ok", bmad_version="6.1.0"),
            "updated_at": LATER,
        }
    )

    repository_adapter(session).update(changed)

    assert row.url == "https://x/renamed.git"
    assert row.default_branch == "develop"
    assert row.install_command == "pnpm i"
    assert row.quality_gate_command == "pnpm lint"
    assert row.unit_test_command == "pnpm test"
    assert row.package_manager == "pnpm"
    assert row.test_globs == [*SUGGESTED_TEST_GLOBS, "e2e/**"]
    assert row.clone_check == {
        "status": "ok",
        "at": LATER.isoformat(),
        "output": "ok",
        "bmad_version": "6.1.0",
    }
    assert row.updated_at == LATER


def test_update_never_moves_the_identity_of_the_row() -> None:
    """The slug identifies the Repository to an Operator; `project_id` and `created_at`
    are history; none of the three is editable."""
    repository = a_repository()
    row = a_row(repository)
    session = RecordingSession([row])

    repository_adapter(session).update(
        repository.model_copy(
            update={"slug": "somewhere-else", "project_id": new_id(), "created_at": LATER}
        )
    )

    assert row.slug == repository.slug
    assert row.project_id == repository.project_id
    assert row.created_at == AT


def test_update_rebuilds_the_json_columns_rather_than_mutating_them() -> None:
    """SQLAlchemy does not track a mutation inside a JSON value; the write would be lost."""
    repository = a_repository()
    row = a_row(repository)
    before_globs = row.test_globs
    before_check = row.clone_check
    session = RecordingSession([row])

    repository_adapter(session).update(
        repository.model_copy(update={"test_globs": (*SUGGESTED_TEST_GLOBS, "x/**")})
    )

    assert row.test_globs is not before_globs
    assert row.clone_check is not before_check


def test_updating_something_that_was_never_added_is_refused_as_the_fake_refuses_it() -> None:
    session = RecordingSession()

    with pytest.raises(ValueError, match="no repository"):
        repository_adapter(session).update(a_repository())


def test_the_clone_check_json_shape_round_trips_a_result() -> None:
    check = CloneCheck(status="ok", at=LATER, output="ok", bmad_version="6.1.0")

    assert clone_check_json(check) == {
        "status": "ok",
        "at": LATER.isoformat(),
        "output": "ok",
        "bmad_version": "6.1.0",
    }


def test_the_pending_clone_check_serialises_with_a_null_timestamp() -> None:
    assert clone_check_json(CloneCheck.pending()) == {
        "status": "pending",
        "at": None,
        "output": "",
        "bmad_version": None,
    }


def test_the_id_column_round_trips_a_uuid() -> None:
    repository = a_repository()

    assert isinstance(to_entity(a_row(repository)).id, UUID)
