"""run.last_opened_before: the prior visit timestamp, used to compute per-file changed marks.

A nullable TIMESTAMPTZ column: `None` (first visit) correctly yields all `changed: false`.
Chains from `0010_terminal_clean_polls` (the current head migration).

Revision ID: 0011_last_opened_before
Revises: 0010_terminal_clean_polls
Create Date: 2026-09-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_last_opened_before"
down_revision: str | None = "0010_terminal_clean_polls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
COLUMN = "last_opened_before"


def upgrade() -> None:
    op.add_column(
        RUN,
        sa.Column(COLUMN, sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column(RUN, COLUMN)
