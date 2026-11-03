"""The SQLAlchemy adapter for the `ProjectChannelRepository` port.

It mirrors `tests/unit/fakes/project_channel.py`: `put` inserts or replaces, and `delete`
of a missing row is a no-op. `put` is one `INSERT … ON CONFLICT DO UPDATE`, so two first
saves racing on one Project cannot fail on the primary key.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatProvider, ChatUser
from orchestrator.infrastructure.db.models.project_channel import ProjectChannelRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

USER_ID_KEY = "id"
USER_HANDLE_KEY = "handle"

#: The columns `put` writes over a stored row. `project_id` and `created_at` are not among them.
MUTABLE_FIELDS = (
    "provider",
    "base_url",
    "channel_id",
    "token_enc",
    "metadata_only",
    "allowed_users",
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

    def get_current(self, project_id: UUID) -> ProjectChannel | None:
        # A chat fire's session keeps its identity map across commits (`expire_on_commit`
        # is off), so `session.get` could return the channel an earlier batch loaded.
        statement = (
            select(ProjectChannelRow)
            .where(ProjectChannelRow.project_id == project_id)
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        return None if row is None else to_entity(row)

    def list_all(self) -> list[ProjectChannel]:
        statement = select(ProjectChannelRow).order_by(ProjectChannelRow.project_id)
        return [to_entity(row) for row in self._session.scalars(statement).all()]

    def put(self, channel: ProjectChannel) -> None:
        values: dict[str, Any] = {
            "project_id": channel.project_id,
            "provider": channel.provider,
            "base_url": channel.base_url,
            "channel_id": channel.channel_id,
            "token_enc": channel.token_enc,
            "allowed_users": allowed_users_json(channel),
            "metadata_only": channel.metadata_only,
            "created_at": channel.created_at,
            "updated_at": channel.updated_at,
        }
        statement = (
            insert(ProjectChannelRow.__table__)
            .values(**values)
            .on_conflict_do_update(
                index_elements=["project_id"],
                set_={name: values[name] for name in MUTABLE_FIELDS},
            )
        )
        self._session.execute(statement)

    def delete(self, project_id: UUID) -> None:
        row = self._session.get(ProjectChannelRow, project_id)
        if row is not None:
            self._session.delete(row)
