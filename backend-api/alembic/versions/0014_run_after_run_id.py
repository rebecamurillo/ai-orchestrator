"""run.after_run_id: the Run that must complete before this one may start (story 5-3).

Revision ID: 0014_run_after_run_id
Revises: 0013_run_partition_branch
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_run_after_run_id"
down_revision: str | None = "0013_run_partition_branch"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run", sa.Column("after_run_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("run", "after_run_id")
