"""analysis and analysis_artifact: what one calculation read of one repository.

Revision ID: 0041_analysis
Revises: 0040_fact_set_subscription
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0041_analysis"
down_revision: str | None = "0040_fact_set_subscription"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

ANALYSIS_TABLE = "analysis"
ARTIFACT_TABLE = "analysis_artifact"
STATUSES = "status IN ('ok', 'partial', 'failed')"


def upgrade() -> None:
    op.create_table(
        ANALYSIS_TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column(
            "calculation_id", sa.Uuid(), sa.ForeignKey("metric_calculation.id"), nullable=False
        ),
        sa.Column("repository_path", sa.Text(), nullable=False),
        sa.Column("base", sa.Text(), nullable=True),
        sa.Column("head", sa.Text(), nullable=True),
        sa.Column("toolset", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("toolset_fingerprint", sa.Text(), nullable=False, server_default=""),
        sa.Column("declaration_hash", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(STATUSES, name=op.f("ck_analysis_status")),
    )
    op.create_index("ix_analysis_run", ANALYSIS_TABLE, ["run_id"])
    op.create_index("ix_analysis_calculation", ANALYSIS_TABLE, ["calculation_id"])
    op.create_table(
        ARTIFACT_TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("analysis_id", sa.Uuid(), sa.ForeignKey(f"{ANALYSIS_TABLE}.id"), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("media_type", sa.Text(), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table(ARTIFACT_TABLE)
    op.drop_table(ANALYSIS_TABLE)
