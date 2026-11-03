"""step_run.consults: AD-22's consult entries, keyed by the stop kind consulted on.

No row stored before this revision ever consulted, so the server default is the backfill.

Revision ID: 0024_step_run_consults
Revises: 0023_attempt_role
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024_step_run_consults"
down_revision: str | None = "0023_attempt_role"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "step_run",
        sa.Column(
            "consults",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("step_run", "consults")
