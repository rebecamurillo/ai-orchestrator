"""The four tables Epic 4 executes over: `run`, `step_run`, `attempt`, `gate_record`.

Four tables and no more, because the ER diagram has four: a Run plans rows, a row executes
attempts, a Run records gates. Every list and every map is `jsonb` — `pinned_versions`,
`inputs`, `plan_refs`, `engine_ref`, `accepted_paths`, `worktrees`, `compare_urls`,
`with_resolved`, `frozen_test_files`, `payload` — because each is short, always read whole
with its row, and never queried into. Money is `numeric(12, 6)` and hours `numeric(10, 2)`
(Consistency Conventions); a float would round a cost the Operator is shown.

The three unique indexes are the guarantees the use cases in 4.4 and 4.6 rely on and the
fakes in `tests/unit/fakes/runs.py` mirror: `(run_id, seq)` and `(run_id, path)` are what
make a plan a list rather than a bag, and `(step_run_id, n)` is what stops a restart from
writing a second attempt 2. The three non-unique ones are the reads: the Board filters by
project, the queue by status, the preflight rule by `(repository, status)`, and the Run
screen reads a gate record by `(run_id, at)`.

Statuses, park kinds, gates and actors are `Text` rather than a database `enum`: the tokens
live in `domain/statuses.py` (AD-8), and a Postgres type would be a second declaration of
them that a migration would have to keep in step.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, Text, Uuid, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.project import ProjectRow
from orchestrator.infrastructure.db.models.repository import RepositoryRow

RUN_TABLE = "run"
STEP_RUN_TABLE = "step_run"
ATTEMPT_TABLE = "attempt"
GATE_RECORD_TABLE = "gate_record"

#: The reads the Board, the queue and the preflight rule make.
RUN_PROJECT_INDEX = "ix_run_project_id"
RUN_STATUS_INDEX = "ix_run_status"
RUN_REPOSITORY_STATUS_INDEX = "ix_run_repository_id_status"

#: What makes a plan a list: one row per `seq` and one per `path`, within one Run.
STEP_RUN_SEQ_INDEX = "ix_step_run_run_id_seq"
STEP_RUN_PATH_INDEX = "ix_step_run_run_id_path"

#: What stops a restart from writing a second attempt at the same number.
ATTEMPT_N_INDEX = "ix_attempt_step_run_id_n"

#: How the Run screen reads a gate record: one Run, in the order things happened.
GATE_RECORD_AT_INDEX = "ix_gate_record_run_id_at"

#: How a terminal transition finds its dependents: `after_run_ids @> ARRAY[predecessor]`.
#: GIN, because the question is containment in an array and no b-tree answers that.
RUN_AFTER_RUN_IDS_INDEX = "ix_run_after_run_ids"

#: Money, and the hours an Operator estimated by hand.
MONEY = Numeric(12, 6)
HOURS = Numeric(10, 2)


class RunRow(Base):
    """One stored Run."""

    __tablename__ = RUN_TABLE
    __table_args__ = (
        Index(RUN_PROJECT_INDEX, "project_id"),
        Index(RUN_STATUS_INDEX, "status"),
        Index(RUN_REPOSITORY_STATUS_INDEX, "repository_id", "status"),
        Index(RUN_AFTER_RUN_IDS_INDEX, "after_run_ids", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{ProjectRow.__tablename__}.id"))
    repository_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{RepositoryRow.__tablename__}.id")
    )
    template_name: Mapped[str] = mapped_column(Text())
    template_version: Mapped[int] = mapped_column(Integer())
    pinned_versions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    inputs: Mapped[dict[str, Any]] = mapped_column(JSONB())
    status: Mapped[str] = mapped_column(Text())
    plan_ref: Mapped[str | None] = mapped_column(Text(), nullable=True)
    plan_refs: Mapped[dict[str, str]] = mapped_column(JSONB())
    engine_ref: Mapped[dict[str, Any]] = mapped_column(JSONB())
    budget_usd: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    spend_usd: Mapped[Decimal] = mapped_column(MONEY)
    spend_provisional: Mapped[bool] = mapped_column(Boolean(), server_default=text("FALSE"))
    manual_estimate_h: Mapped[Decimal | None] = mapped_column(HOURS, nullable=True)
    re_review_done: Mapped[bool] = mapped_column(Boolean())
    park_kind: Mapped[str | None] = mapped_column(Text(), nullable=True)
    park_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    park_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    accepted_paths: Mapped[list[str]] = mapped_column(JSONB())
    worktree_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    worktrees: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    compare_urls: Mapped[list[str]] = mapped_column(JSONB())
    trace_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    terminal_session: Mapped[bool] = mapped_column(Boolean())
    terminal_clean_polls: Mapped[int] = mapped_column(Integer())
    active_seconds: Mapped[int] = mapped_column(Integer())
    last_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_before: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worktrees_removed: Mapped[bool] = mapped_column(Boolean())
    partition_branch: Mapped[str | None] = mapped_column(Text(), nullable=True)
    #: The fan-in predecessor list (AD-12, spine amendment 2026-09-23). A real `uuid[]`
    #: rather than `jsonb`, unlike every other list on this table, because this one *is*
    #: queried into: `list_dependents` asks which Runs name a predecessor, and only an
    #: array column answers that with an index. No foreign key — an array cannot carry one
    #: in Postgres, which is why `resolve_dependent` decides for itself what a dangling id
    #: means (`writers.DEPENDENCY_MISSING_REASON`).
    after_run_ids: Mapped[list[UUID]] = mapped_column(
        ARRAY(Uuid()), server_default=text("'{}'::uuid[]")
    )


class StepRunRow(Base):
    """One stored planned row of a Run."""

    __tablename__ = STEP_RUN_TABLE
    __table_args__ = (
        Index(STEP_RUN_SEQ_INDEX, "run_id", "seq", unique=True),
        Index(STEP_RUN_PATH_INDEX, "run_id", "path", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    seq: Mapped[int] = mapped_column(Integer())
    path: Mapped[str] = mapped_column(Text())
    label: Mapped[str] = mapped_column(Text())
    kind: Mapped[str] = mapped_column(Text())
    gate: Mapped[str] = mapped_column(Text())
    status: Mapped[str] = mapped_column(Text())
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    with_resolved: Mapped[dict[str, Any]] = mapped_column(JSONB())
    retry_count: Mapped[int] = mapped_column(Integer())
    redispatch_count: Mapped[int] = mapped_column(Integer())
    frame: Mapped[str | None] = mapped_column(Text(), nullable=True)
    story_id: Mapped[str | None] = mapped_column(Text(), nullable=True)


class AttemptRow(Base):
    """One stored attempt at one row. Written in two halves (AD-8)."""

    __tablename__ = ATTEMPT_TABLE
    __table_args__ = (Index(ATTEMPT_N_INDEX, "step_run_id", "n", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    step_run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{STEP_RUN_TABLE}.id"))
    n: Mapped[int] = mapped_column(Integer())
    status: Mapped[str] = mapped_column(Text())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    engine_ref: Mapped[dict[str, Any]] = mapped_column(JSONB())
    start_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    end_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # The worktree root's own range, written only when the row declares `workdir` (AD-17's
    # "one attempt spans two trees", hub-Run initiative workflow H4, 2026-09-23).
    root_start_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    root_end_sha: Mapped[str | None] = mapped_column(Text(), nullable=True)
    frozen_test_files: Mapped[list[str] | None] = mapped_column(JSONB(), nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    output_ref: Mapped[str | None] = mapped_column(Text(), nullable=True)
    harness: Mapped[str | None] = mapped_column(Text(), nullable=True)
    model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    session_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    pgid: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    cost_usd: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    cost_provisional: Mapped[bool] = mapped_column(Boolean())


class GateRecordRow(Base):
    """One appended line of a Run's gate record. Nothing updates or deletes one."""

    __tablename__ = GATE_RECORD_TABLE
    __table_args__ = (Index(GATE_RECORD_AT_INDEX, "run_id", "at"),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    event: Mapped[str] = mapped_column(Text())
    actor: Mapped[str] = mapped_column(Text())
    text: Mapped[str] = mapped_column(Text())
    attempt_n: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB())
