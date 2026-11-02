"""The SQLAlchemy adapter for the `ProjectChannelRepository` port.

It mirrors `tests/unit/fakes/project_channel.py`: `put` inserts or replaces, and `delete`
of a missing row is a no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatProvider, ChatUser
from orchestrator.infrastructure.db.models.project_channel import ProjectChannelRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

USER_ID_KEY = "id"
USER_HANDLE_KEY = "handle"

#: The fields `put` writes over a stored row. `project_id` and `created_at` are not among them.
MUTABLE_FIELDS = (
    "provider",
    "base_url",
    "channel_id",
    "token_enc",
    "metadata_only",
    "updated_at",
)


def to_entity(row: ProjectChannelRow) -> ProjectChannel:
    return ProjectChannel(
        project_id=row.project_id,
        provider=cast(ChatProvider, row.provider),
        base_url=row.base_url,
        channel_id=row.channel_id,
        token_enc=row.token_enc,
        allowed_users=tuple(
            ChatUser(id=item[USER_ID_KEY], handle=item[USER_HANDLE_KEY])
            for item in row.allowed_users
        ),
        metadata_only=row.metadata_only,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def allowed_users_json(channel: ProjectChannel) -> list[dict[str, Any]]:
    return [{USER_ID_KEY: user.id, USER_HANDLE_KEY: user.handle} for user in channel.allowed_users]


class SQLAlchemyProjectChannelRepository:
    """Stored chat channels, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, project_id: UUID) -> ProjectChannel | None:
        row = self._session.get(ProjectChannelRow, project_id)
        return None if row is None else to_entity(row)

    def put(self, channel: ProjectChannel) -> None:
        row = self._session.get(ProjectChannelRow, channel.project_id)
        if row is None:
            self._session.add(
                ProjectChannelRow(
                    project_id=channel.project_id,
                    created_at=channel.created_at,
                    allowed_users=allowed_users_json(channel),
                    **{name: getattr(channel, name) for name in MUTABLE_FIELDS},
                )
            )
            return
        for name in MUTABLE_FIELDS:
            setattr(row, name, getattr(channel, name))
        # rebuilt rather than mutated: SQLAlchemy does not track a change inside a JSON value
        row.allowed_users = allowed_users_json(channel)

    def delete(self, project_id: UUID) -> None:
        row = self._session.get(ProjectChannelRow, project_id)
        if row is not None:
            self._session.delete(row)
