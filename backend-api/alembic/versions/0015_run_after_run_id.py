"""run.after_run_id: the Run this one waits for before the start Signal may enqueue it (story 5-3).

Added so the `start` signal handler can clear it; story 5-4 adds the setter. Always NULL in
story 5-3's scope — clearing NULL → NULL is a no-op that seeds the 5-4 invariant correctly.

Revision ID: 0014_run_after_run_id
Revises: 0013_run_partition_branch
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_run_after_run_id"
down_revision: str | None = "0014_run_partition_branch"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run", sa.Column("after_run_id", sa.dialects.postgresql.UUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("run", "after_run_id")
