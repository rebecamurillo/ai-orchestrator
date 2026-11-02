"""attempt.role: who an attempt ran for — `agent`, `consult` or `session` (AD-21).

Every attempt stored before this revision was an agent's, so the server default is the backfill.

Revision ID: 0023_attempt_role
Revises: 0022_run_park_seq
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_attempt_role"
down_revision: str | None = "0022_run_park_seq"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "attempt",
        sa.Column("role", sa.Text(), server_default="agent", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("attempt", "role")
