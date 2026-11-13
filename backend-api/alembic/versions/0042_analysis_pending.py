"""analysis without a calculation, and the analyses a result version used.

Revision ID: 0042_analysis_pending
Revises: 0041_analysis
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0042_analysis_pending"
down_revision: str | None = "0041_analysis"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("analysis", "calculation_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "result_version",
        sa.Column("analysis_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("result_version", "analysis_ids")
    op.execute(
        "DELETE FROM analysis_artifact WHERE analysis_id IN "
        "(SELECT id FROM analysis WHERE calculation_id IS NULL)"
    )
    op.execute("DELETE FROM analysis WHERE calculation_id IS NULL")
    op.alter_column("analysis", "calculation_id", existing_type=sa.Uuid(), nullable=False)
