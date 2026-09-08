"""trajectory: one append-only row per Story that reaches `done` (SPEC CAP-9, AD-19, FR-32).

`attempts`, `gate_results` and `human_actions` are `jsonb`, matching the earlier tables'
own precedent for short, whole-read structures. `cost_usd` is `numeric(12, 6)`, the same
money scale `run.budget_usd`/`attempt.cost_usd` already use. The unique index on
`(run_id, frame)` is what `record_trajectory` relies on to stay idempotent on a
durable-step replay (AD-19, AD-6).

Revision ID: 0009_trajectory
Revises: 0008_harness_readiness
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_trajectory"
down_revision: str | None = "0008_harness_readiness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRAJECTORY = "trajectory"
RUN_FRAME_UNIQUE = "uq_trajectory_run_id_frame"


def upgrade() -> None:
    op.create_table(
        TRAJECTORY,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Text(), nullable=True),
        sa.Column("epic_index", sa.Integer(), nullable=False),
        sa.Column("frame", sa.Text(), nullable=False),
        sa.Column("harness", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("attempts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("gate_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("tokens_in", sa.Integer(), nullable=False),
        sa.Column("tokens_out", sa.Integer(), nullable=False),
        sa.Column("wall_clock_seconds", sa.Float(), nullable=False),
        sa.Column("story_file", sa.Text(), nullable=False),
        sa.Column("start_sha", sa.Text(), nullable=True),
        sa.Column("end_sha", sa.Text(), nullable=True),
        sa.Column("human_actions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "frame", name=RUN_FRAME_UNIQUE),
    )


def downgrade() -> None:
    op.drop_table(TRAJECTORY)
