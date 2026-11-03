"""`SQLAlchemyProjectChannelRepository.put` is one upsert (story 3-4 review, 2026-11-02).

Two concurrent first saves would both find no row and both insert; one statement with
`ON CONFLICT (project_id) DO UPDATE` lets the second replace the first instead of failing on
the primary key. `created_at` survives the replace.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.dialects import postgresql

from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser
from orchestrator.infrastructure.db import SQLAlchemyProjectChannelRepository

AT = datetime(2026, 11, 2, 9, 0, tzinfo=UTC)


class ExecutingSession:
    """Records the statements `put` executes, and refuses the ORM add path."""

    def __init__(self) -> None:
        self.executed: list[Any] = []

    def execute(self, statement: Any) -> None:
        self.executed.append(statement)

    def add(self, row: object) -> None:
        raise AssertionError("put must not add through the ORM: two first saves would race")

    def get(self, entity: type, key: Any) -> None:
        raise AssertionError("put must not read before it writes")


def a_channel() -> ProjectChannel:
    return ProjectChannel(
        project_id=new_id(),
        provider="mattermost",
        base_url="https://chat.example.com",
        channel_id="c1",
        token_enc="gAAAAA-ciphertext",
        allowed_users=(ChatUser(id="u1", handle="alice"),),
        metadata_only=True,
        created_at=AT,
        updated_at=AT,
    )


def put(channel: ProjectChannel) -> tuple[str, dict[str, Any]]:
    session = ExecutingSession()
    SQLAlchemyProjectChannelRepository(session).put(channel)  # type: ignore[arg-type]
    (statement,) = session.executed
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), dict(compiled.params)


def test_put_is_one_insert_that_updates_on_a_project_id_conflict() -> None:
    sql, _ = put(a_channel())

    assert sql.startswith("INSERT INTO project_channel ")
    assert "ON CONFLICT (project_id) DO UPDATE SET " in sql


def test_the_insert_carries_every_column() -> None:
    channel = a_channel()

    _, params = put(channel)

    assert params["project_id"] == channel.project_id
    assert params["provider"] == "mattermost"
    assert params["base_url"] == "https://chat.example.com"
    assert params["channel_id"] == "c1"
    assert params["token_enc"] == "gAAAAA-ciphertext"
    assert params["allowed_users"] == [{"id": "u1", "handle": "alice"}]
    assert params["metadata_only"] is True
    assert params["created_at"] == AT
    assert params["updated_at"] == AT


def test_the_update_keeps_the_key_and_the_creation_time() -> None:
    sql, _ = put(a_channel())

    updated = sql.split("DO UPDATE SET ", 1)[1]
    assert "project_id =" not in updated
    assert "created_at =" not in updated
    for column in (
        "provider",
        "base_url",
        "channel_id",
        "token_enc",
        "allowed_users",
        "metadata_only",
        "updated_at",
    ):
        assert f"{column} = " in updated
