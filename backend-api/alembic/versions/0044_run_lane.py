"""run.lane: the engine queue a Run waits in (`walk` or `interactive`).

Revision ID: 0044_run_lane
Revises: 0043_attempt_log_removed
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0044_run_lane"
down_revision: str | None = "0043_attempt_log_removed"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column("lane", sa.Text(), nullable=False, server_default=sa.text("'walk'")),
    )


def downgrade() -> None:
    op.drop_column("run", "lane")
