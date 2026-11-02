"""In-memory `ProjectChannelRepository` — the one fake for that port (AD-18). Reuse it.

Stories 3-3 and 4-1 read the stored channel through this fake as well. It mirrors the
table: one row per Project, `put` inserts or replaces, and `delete` of a missing row is a
no-op, as a `DELETE` matching nothing is.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.entities.project_channel import ProjectChannel


class FakeProjectChannelRepository:
    """Stored channels in a dictionary, keyed by Project id."""

    def __init__(self, channels: list[ProjectChannel] | None = None) -> None:
        self.channels: dict[UUID, ProjectChannel] = {}
        self.deleted: list[UUID] = []
        for channel in channels or []:
            self.put(channel)

    def get(self, project_id: UUID) -> ProjectChannel | None:
        return self.channels.get(project_id)

    def list_all(self) -> list[ProjectChannel]:
        """Every stored channel, ordered by `project_id` as the adapter's `ORDER BY` is."""
        return [self.channels[key] for key in sorted(self.channels)]

    def put(self, channel: ProjectChannel) -> None:
        self.channels[channel.project_id] = channel

    def delete(self, project_id: UUID) -> None:
        self.deleted.append(project_id)
        self.channels.pop(project_id, None)
