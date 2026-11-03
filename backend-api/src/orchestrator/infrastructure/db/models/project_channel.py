"""The `project_channel` table (AD-25): one row per Project with a chat channel.

No row means `off`. `token_enc` is a Fernet token (AD-5 amendment), and no plaintext token
is ever written here. The row goes with its Project (`ON DELETE CASCADE`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.project import TABLE_NAME as PROJECT_TABLE

PROJECT_CHANNEL_TABLE = "project_channel"

#: The platforms a stored row may name; `off` is the absence of a row.
PROVIDER_CHECK = "provider IN ('mattermost', 'slack')"


class ProjectChannelRow(Base):
    """One stored chat channel."""

    __tablename__ = PROJECT_CHANNEL_TABLE
    __table_args__ = (CheckConstraint(PROVIDER_CHECK, name="provider"),)

    project_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{PROJECT_TABLE}.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(Text())
    base_url: Mapped[str] = mapped_column(Text())
    channel_id: Mapped[str] = mapped_column(Text())
    token_enc: Mapped[str] = mapped_column(Text())
    allowed_users: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    metadata_only: Mapped[bool] = mapped_column(Boolean())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
