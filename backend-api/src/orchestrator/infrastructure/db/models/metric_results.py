"""`metric_calculation`, `result_version` and `metric_value` (AGENTS.md "Data capture").

Only a calculation's state, start, end and output are ever updated; versions and values are
written once.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.run import RUN_TABLE

CALCULATION_TABLE = "metric_calculation"
VERSION_TABLE = "result_version"
VALUE_TABLE = "metric_value"
VERSION_UNIQUE = "uq_result_version_run_n"
FIGURE_OR_WORD_CHECK = "figure_or_word"
FIGURE_OR_WORD = "value_num IS NULL OR missing IS NULL OR missing = 'partial'"
STATE_CHECK = "state"
STATES = "state IN ('queued', 'running', 'failed', 'done')"


class MetricCalculationRow(Base):
    __tablename__ = CALCULATION_TABLE
    __table_args__ = (
        CheckConstraint(STATES, name=STATE_CHECK),
        Index("ix_metric_calculation_run_state", "run_id", "state"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    target_n: Mapped[int] = mapped_column(Integer())
    state: Mapped[str] = mapped_column(Text())
    entry_point: Mapped[list[str]] = mapped_column(JSONB())
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    output: Mapped[str] = mapped_column(Text(), default="")


class ResultVersionRow(Base):
    __tablename__ = VERSION_TABLE
    __table_args__ = (UniqueConstraint("run_id", "n", name=VERSION_UNIQUE),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    n: Mapped[int] = mapped_column(Integer())
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_point: Mapped[list[str]] = mapped_column(JSONB())
    methods: Mapped[list[str]] = mapped_column(JSONB())
    fact_set_ids: Mapped[list[Any]] = mapped_column(JSONB())
    analysis_ids: Mapped[list[Any]] = mapped_column(JSONB(), default=list)
    toolset_fingerprint: Mapped[str | None] = mapped_column(Text(), nullable=True)


class MetricValueRow(Base):
    __tablename__ = VALUE_TABLE
    __table_args__ = (
        CheckConstraint(FIGURE_OR_WORD, name=FIGURE_OR_WORD_CHECK),
        Index("ix_metric_value_version", "version_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    version_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{VERSION_TABLE}.id"))
    metric_id: Mapped[str] = mapped_column(Text())
    method_id: Mapped[str] = mapped_column(Text())
    scope_type: Mapped[str] = mapped_column(Text())
    scope_key: Mapped[str] = mapped_column(Text())
    scope_label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    role: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    repository: Mapped[str | None] = mapped_column(Text(), nullable=True)
    attempt_n: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    source: Mapped[str | None] = mapped_column(Text(), nullable=True)
    value_num: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    unit: Mapped[str] = mapped_column(Text())
    missing: Mapped[str | None] = mapped_column(Text(), nullable=True)
    partial_n: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    partial_m: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    carried_from: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    project_id: Mapped[UUID] = mapped_column(Uuid())
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    template_name: Mapped[str] = mapped_column(Text())
    template_version: Mapped[int] = mapped_column(Integer())
    harness: Mapped[str | None] = mapped_column(Text(), nullable=True)
    harness_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
    origin_model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    origin_model_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
    origin_repository: Mapped[str | None] = mapped_column(Text(), nullable=True)
    origin_repository_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
    branch: Mapped[str | None] = mapped_column(Text(), nullable=True)
    branch_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
    commit: Mapped[str | None] = mapped_column(Text(), nullable=True)
    commit_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
    base_commit: Mapped[str | None] = mapped_column(Text(), nullable=True)
    base_commit_na: Mapped[str | None] = mapped_column(Text(), nullable=True)
