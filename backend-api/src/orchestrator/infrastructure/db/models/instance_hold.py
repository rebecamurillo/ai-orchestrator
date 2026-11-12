"""The `instance_hold` table (SPEC CAP-4, AD-30): at most one row, written by the hold use case."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base

INSTANCE_HOLD_TABLE = "instance_hold"


class InstanceHoldRow(Base):
    __tablename__ = INSTANCE_HOLD_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    held_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str] = mapped_column(Text())
