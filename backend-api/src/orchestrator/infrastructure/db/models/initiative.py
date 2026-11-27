"""The `initiative` and `initiative_advance` tables (AD-36). No column holds a status."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base

INITIATIVE_TABLE = "initiative"
INITIATIVE_ADVANCE_TABLE = "initiative_advance"

#: One open initiative per `(repository, slug)`; a cancelled one frees the slug.
INITIATIVE_SLUG_INDEX = "uq_initiative_repository_slug_open"
#: One advance per `(initiative, round, position)`.
INITIATIVE_ADVANCE_KEY = "uq_initiative_advance_initiative_id_round_position"


class InitiativeRow(Base):
    """One stored initiative."""

    __tablename__ = INITIATIVE_TABLE
    __table_args__ = (
        Index(
            INITIATIVE_SLUG_INDEX,
            "repository_id",
            "slug",
            unique=True,
            postgresql_where=text("cancelled_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("project.id"))
    repository_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("repository.id"))
    slug: Mapped[str] = mapped_column(Text())
    name: Mapped[str] = mapped_column(Text())
    first_message: Mapped[str] = mapped_column(Text())
    sequence: Mapped[dict[str, Any]] = mapped_column(JSONB())
    round: Mapped[int] = mapped_column(Integer(), server_default="1")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    branch_cleanup_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    pr_merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InitiativeAdvanceRow(Base):
    """One stored advance."""

    __tablename__ = INITIATIVE_ADVANCE_TABLE
    __table_args__ = (
        UniqueConstraint("initiative_id", "round", "position", name=INITIATIVE_ADVANCE_KEY),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    initiative_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("initiative.id"))
    from_run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("run.id"))
    round: Mapped[int] = mapped_column(Integer())
    position: Mapped[int] = mapped_column(Integer())
    blocked_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
