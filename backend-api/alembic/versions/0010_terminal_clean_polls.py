"""run.terminal_clean_polls: how many consecutive clean polls a terminal session has had.

One `NOT NULL` column, defaulted `0` for every existing row. `terminal_poll` (SPEC CAP-7,
FR-21) increments it while the Story file reads `done` and the worktree is clean, resets it
to `0` the moment either stops being true, and spends it back to `0` when it reaches two and
sends `terminal_resume` — so a later terminal session on the same Run starts from nothing.

Not a nullable column: `tests/unit/test_run_repository_adapter.py`'s own
`test_only_the_columns_a_later_story_fills_may_be_null` is a frozen, closed set of the `run`
table's nullable columns (hard rule 1), and `0007_run_gc` already recorded that a `NOT NULL`
column with a server default is how a counter or a flag joins this table without touching it.

Revision ID: 0010_terminal_clean_polls
Revises: 0009_trajectory
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_terminal_clean_polls"
down_revision: str | None = "0009_trajectory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
COLUMN = "terminal_clean_polls"


def upgrade() -> None:
    op.add_column(
        RUN,
        sa.Column(COLUMN, sa.Integer(), nullable=False, server_default=sa.text("0")),
    )


def downgrade() -> None:
    op.drop_column(RUN, COLUMN)
