"""The `trajectory` table (SPEC CAP-9, AD-19): one append-only row per Story reaching `done`.

`attempts`, `gate_results` and `human_actions` are `jsonb` — each is short, always read
whole with its row, and never queried into (`models/run.py`'s own precedent). `cost_usd`
reuses that module's `MONEY` (`numeric(12, 6)`, Consistency Conventions). The unique index on
`(run_id, frame)` is the guarantee `record_trajectory` relies on to stay idempotent on
replay, restated at the table itself for a caller that reaches the database directly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.run import MONEY, RUN_TABLE

TRAJECTORY_TABLE = "trajectory"

#: What stops `record_trajectory` from ever landing a second row for the same Story frame.
TRAJECTORY_RUN_FRAME_UNIQUE = "uq_trajectory_run_id_frame"


class TrajectoryRow(Base):
    """One stored Trajectory. Nothing updates or deletes one (AD-19)."""

    __tablename__ = TRAJECTORY_TABLE
    __table_args__ = (UniqueConstraint("run_id", "frame", name=TRAJECTORY_RUN_FRAME_UNIQUE),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    project_id: Mapped[UUID] = mapped_column(Uuid())
    repository_id: Mapped[UUID] = mapped_column(Uuid())
    story_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    epic_index: Mapped[int] = mapped_column(Integer())
    frame: Mapped[str] = mapped_column(Text())
    harness: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    attempts: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    gate_results: Mapped[dict[str, Any]] = mapped_column(JSONB())
    cost_usd: Mapped[Decimal] = mapped_column(MONEY)
    tokens_in: Mapped[int] = mapped_column(Integer())
    tokens_out: Mapped[int] = mapped_column(Integer())
    wall_clock_seconds: Mapped[float] = mapped_column(Float())
    story_file: Mapped[str] = mapped_column(Text())
    start_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    end_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    human_actions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
