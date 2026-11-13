"""`analysis` and `analysis_artifact`: written once, never updated or deleted."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, LargeBinary, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.metric_results import CALCULATION_TABLE
from orchestrator.infrastructure.db.models.run import RUN_TABLE

ANALYSIS_TABLE = "analysis"
ARTIFACT_TABLE = "analysis_artifact"
STATUS_CHECK = "status"
STATUSES = "status IN ('ok', 'partial', 'failed')"


class AnalysisRow(Base):
    __tablename__ = ANALYSIS_TABLE
    __table_args__ = (
        CheckConstraint(STATUSES, name=STATUS_CHECK),
        Index("ix_analysis_run", "run_id"),
        Index("ix_analysis_calculation", "calculation_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    calculation_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{CALCULATION_TABLE}.id"))
    repository_path: Mapped[str] = mapped_column(Text())
    base: Mapped[str | None] = mapped_column(Text(), nullable=True)
    head: Mapped[str | None] = mapped_column(Text(), nullable=True)
    toolset: Mapped[list[Any]] = mapped_column(JSONB())
    toolset_fingerprint: Mapped[str] = mapped_column(Text(), default="")
    declaration_hash: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[str] = mapped_column(Text())
    output: Mapped[str] = mapped_column(Text(), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AnalysisArtifactRow(Base):
    __tablename__ = ARTIFACT_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    analysis_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{ANALYSIS_TABLE}.id"))
    tool: Mapped[str] = mapped_column(Text())
    media_type: Mapped[str] = mapped_column(Text())
    body: Mapped[bytes] = mapped_column(LargeBinary())
