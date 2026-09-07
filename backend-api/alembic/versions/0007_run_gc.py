"""run.worktrees_removed: whether `worktree_gc` has already swept a terminal Run.

One `NOT NULL` column, defaulted `false` for every existing row. `worktree_gc` (SPEC
CAP-11, FR-9) reads it to skip a Run it already swept — the sweep is idempotent because the
column starts `false` and only ever flips once, never back.

Not a nullable timestamp, which is what this story's brief suggested
(`worktrees_removed_at`): `tests/unit/test_run_repository_adapter.py`'s own
`test_only_the_columns_a_later_story_fills_may_be_null` is a frozen, closed set of the
`run` table's nullable columns (hard rule 1 — anchors, existing test files included, are
read-only, and this one names no later story as its replacement, so none of the three
narrow exceptions applies). A `NOT NULL` boolean reaches the same idempotency without
joining that set, and `run.worktrees` is left untouched as history rather than cleared, so
a swept Run's own record still says which branch it worked on after the files are gone.

Revision ID: 0007_run_gc
Revises: 0006_harness
Create Date: 2026-09-07
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_run_gc"
down_revision: str | None = "0006_harness"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
COLUMN = "worktrees_removed"


def upgrade() -> None:
    op.add_column(
        RUN,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column(RUN, COLUMN)
