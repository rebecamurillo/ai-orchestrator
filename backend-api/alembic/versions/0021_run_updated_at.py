"""run.updated_at: the change token the long-poll events route holds a connection against.

The column is the database's, not the application's: `server_default`/`onupdate` are
`now()`, so every `UPDATE` of a Run row advances it without any use case naming it, and no
status writer changes (AD-8). Existing rows take the migration's own timestamp.

Revision ID: 0021_run_updated_at
Revises: 0020_drop_run_initiative
Create Date: 2026-10-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_run_updated_at"
down_revision: str | None = "0020_drop_run_initiative"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("run", "updated_at")
