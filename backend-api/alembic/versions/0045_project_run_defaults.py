"""project.default_*: the defaults a Project's build Run starts with.

Revision ID: 0045_project_run_defaults
Revises: 0044_run_lane
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0045_project_run_defaults"
down_revision: str | None = "0044_run_lane"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project", sa.Column("default_budget_usd", sa.Numeric(12, 6), nullable=True))
    op.add_column("project", sa.Column("default_harness", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("default_model", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("default_autonomy", sa.Text(), nullable=True))
    op.add_column("project", sa.Column("default_senior_model", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("project", "default_senior_model")
    op.drop_column("project", "default_autonomy")
    op.drop_column("project", "default_model")
    op.drop_column("project", "default_harness")
    op.drop_column("project", "default_budget_usd")
