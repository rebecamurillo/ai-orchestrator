"""attempt.log_removed_at: when the retention sweep removed the attempt's log file.

Revision ID: 0043_attempt_log_removed
Revises: 0042_analysis_pending
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0043_attempt_log_removed"
down_revision: str | None = "0042_analysis_pending"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attempt", sa.Column("log_removed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("attempt", "log_removed_at")
