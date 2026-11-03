"""run.pause_requested: a pause waiting for the row now executing to end (AD-13).

No stored Run has asked for one, so the server default is the backfill.

Revision ID: 0025_run_pause_requested
Revises: 0024_step_run_consults
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_run_pause_requested"
down_revision: str | None = "0024_step_run_consults"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column("pause_requested", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("run", "pause_requested")
