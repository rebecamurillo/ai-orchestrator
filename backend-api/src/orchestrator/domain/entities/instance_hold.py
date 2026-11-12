"""The instance hold (SPEC CAP-4, AD-30): at most one row, active until `expires_at`."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InstanceHold(BaseModel):
    """A hold an upgrade places so that no step starts until it is deleted or expires."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    held_at: datetime
    expires_at: datetime
    reason: str

    def active(self, now: datetime) -> bool:
        return self.expires_at > now
