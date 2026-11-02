"""run.park_seq: the number of a Run's current stop (AD-24).

Existing rows start at 0, except a Run parked at the upgrade: it is at a stop, so it takes 1.

Revision ID: 0022_run_park_seq
Revises: 0021_run_updated_at
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_run_park_seq"
down_revision: str | None = "0021_run_updated_at"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column("park_seq", sa.Integer(), server_default="0", nullable=False),
    )
    op.execute("UPDATE run SET park_seq = 1 WHERE park_kind IS NOT NULL")


def downgrade() -> None:
    op.drop_column("run", "park_seq")
