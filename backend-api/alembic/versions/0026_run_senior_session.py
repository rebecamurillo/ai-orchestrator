"""run.senior_session: the Operator's senior session holds the Run (AD-23).

No stored Run has opened one, so the server default is the backfill.

Revision ID: 0026_run_senior_session
Revises: 0025_run_pause_requested
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_run_senior_session"
down_revision: str | None = "0025_run_pause_requested"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column("senior_session", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("run", "senior_session")
