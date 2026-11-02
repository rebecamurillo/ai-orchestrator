"""The `project_channel` table, its migration and its adapter, without a database (story 3-4).

The table is read off `Base.metadata`, the object Alembic compares against. The migration is
run against a recording `op`. The adapter is driven over a session double that records
calls instead of executing SQL, as `test_project_repository_adapter.py` does.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from types import ModuleType
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Boolean, CheckConstraint, DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB

from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.domain.ports.repositories import ProjectChannelRepository
from orchestrator.infrastructure.db import (
    Base,
    ProjectChannelRow,
    SQLAlchemyProjectChannelRepository,
)
from orchestrator.infrastructure.db.repositories.project_channel import (
    allowed_users_json,
    to_entity,
)
from tests.unit.conftest import REPO_ROOT

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)
TABLE = Base.metadata.tables["project_channel"]
MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0028_project_channel.py"


def a_channel(**overrides: object) -> ProjectChannel:
    fields: dict[str, object] = {
        "project_id": new_id(),
        "provider": "mattermost",
        "base_url": "https://chat.example.com",
        "channel_id": "c1",
        "token_enc": "gAAAAA-ciphertext",
        "allowed_users": (ChatUser(id="u1", handle="alice"), ChatUser(id="u2", handle="bob")),
        "metadata_only": True,
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return ProjectChannel(**fields)  # type: ignore[arg-type]


class RecordingSession:
    """A stand-in for `sqlalchemy.orm.Session`: it records, it does not connect."""

    def __init__(self, rows: list[ProjectChannelRow] | None = None) -> None:
        self.rows = list(rows or [])
        self.added: list[ProjectChannelRow] = []
        self.deleted: list[ProjectChannelRow] = []

    def add(self, row: ProjectChannelRow) -> None:
        self.added.append(row)
        self.rows.append(row)

    def get(self, entity: type, key: Any) -> ProjectChannelRow | None:
        assert entity is ProjectChannelRow
        return next((row for row in self.rows if row.project_id == key), None)

    def delete(self, row: ProjectChannelRow) -> None:
        self.deleted.append(row)
        self.rows.remove(row)


def repository(session: RecordingSession) -> SQLAlchemyProjectChannelRepository:
    return SQLAlchemyProjectChannelRepository(session)  # type: ignore[arg-type]


# ── the table ────────────────────────────────────────────────────────────────


def test_the_table_carries_exactly_the_stored_fields() -> None:
    assert set(TABLE.columns.keys()) == {
        "project_id",
        "provider",
        "base_url",
        "channel_id",
        "token_enc",
        "allowed_users",
        "metadata_only",
        "created_at",
        "updated_at",
    }


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("project_id", Uuid),
        ("provider", Text),
        ("base_url", Text),
        ("channel_id", Text),
        ("token_enc", Text),
        ("allowed_users", JSONB),
        ("metadata_only", Boolean),
        ("created_at", DateTime),
        ("updated_at", DateTime),
    ],
)
def test_every_column_has_its_type_and_is_not_null(column: str, kind: type) -> None:
    assert isinstance(TABLE.columns[column].type, kind)
    assert TABLE.columns[column].nullable is False


def test_the_project_id_is_the_key_and_cascades_from_the_project() -> None:
    assert [column.name for column in TABLE.primary_key.columns] == ["project_id"]
    (foreign_key,) = TABLE.columns["project_id"].foreign_keys
    assert foreign_key.target_fullname == "project.id"
    assert foreign_key.ondelete == "CASCADE"


def test_the_provider_is_checked_to_the_two_platforms() -> None:
    checks = [c for c in TABLE.constraints if isinstance(c, CheckConstraint)]

    assert len(checks) == 1
    assert str(checks[0].sqltext) == "provider IN ('mattermost', 'slack')"


# ── the migration ────────────────────────────────────────────────────────────


class RecordingOp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str) -> Any:
        def record(*args: Any, **kwargs: Any) -> Any:
            self.calls.append((name, args, kwargs))
            return args[0] if name == "f" else None

        return record


def load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_0028", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_migration_revises_the_head_before_it() -> None:
    module = load_migration()

    assert module.revision == "0028_project_channel"
    assert module.down_revision == "0027_attempt_session_text"


def test_the_migration_creates_the_table_and_writes_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No row is written, so every existing Project reads `off` after the upgrade."""
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.upgrade()

    names = [name for name, _, _ in recorder.calls if name != "f"]
    assert names == ["create_table"]
    _, args, _ = next(call for call in recorder.calls if call[0] == "create_table")
    assert args[0] == "project_channel"
    rendered = repr(args)
    assert "CASCADE" in rendered
    (check,) = [arg for arg in args if isinstance(arg, CheckConstraint)]
    assert str(check.sqltext) == "provider IN ('mattermost', 'slack')"
    assert check.name == "ck_project_channel_provider"
    columns = [arg for arg in args[1:] if hasattr(arg, "nullable")]
    assert {column.name for column in columns} == set(TABLE.columns.keys())
    assert all(column.nullable is False for column in columns)


def test_the_downgrade_drops_the_table(monkeypatch: pytest.MonkeyPatch) -> None:
    module = load_migration()
    recorder = RecordingOp()
    monkeypatch.setattr(module, "op", recorder)

    module.downgrade()

    assert [(name, args) for name, args, _ in recorder.calls] == [
        ("drop_table", ("project_channel",))
    ]


# ── the adapter ──────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port() -> None:
    assert isinstance(repository(RecordingSession()), ProjectChannelRepository)


def a_row(channel: ProjectChannel) -> ProjectChannelRow:
    return ProjectChannelRow(
        project_id=channel.project_id,
        provider=channel.provider,
        base_url=channel.base_url,
        channel_id=channel.channel_id,
        token_enc=channel.token_enc,
        allowed_users=allowed_users_json(channel),
        metadata_only=channel.metadata_only,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


# Revised: story 3-4 review, 2026-11-02 — `put` became one upsert, so the two tests that
# pinned its ORM add-then-update path are replaced. The statement is pinned in
# `test_project_channel_upsert.py`; the row-to-entity mapping they covered is pinned here.
def test_a_stored_row_reads_back_as_the_channel_it_was_built_from() -> None:
    channel = a_channel()
    session = RecordingSession([a_row(channel)])

    assert session.rows[0].allowed_users == [
        {"id": "u1", "handle": "alice"},
        {"id": "u2", "handle": "bob"},
    ]
    assert to_entity(session.rows[0]) == channel
    assert repository(session).get(channel.project_id) == channel


def test_a_get_of_no_row_is_none() -> None:
    assert repository(RecordingSession()).get(UUID(int=7)) is None


def test_a_delete_removes_the_row_and_a_second_is_a_no_op() -> None:
    # Revised: story 3-4 review, 2026-11-02 — seeded directly, since `put` no longer adds
    channel = a_channel()
    session = RecordingSession([a_row(channel)])

    repository(session).delete(channel.project_id)
    repository(session).delete(channel.project_id)

    assert len(session.deleted) == 1
    assert repository(session).get(channel.project_id) is None
