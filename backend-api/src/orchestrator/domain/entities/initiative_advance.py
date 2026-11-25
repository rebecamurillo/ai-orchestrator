"""The record that an initiative's next workflow is due (AD-36)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InitiativeAdvance(BaseModel):
    """One advance, unique on `(initiative_id, round, position)`."""

    model_config = ConfigDict(frozen=True)

    id: UUID
    initiative_id: UUID
    from_run_id: UUID
    round: int
    position: int
    blocked_reason: str | None = None
    consumed_at: datetime | None = None
