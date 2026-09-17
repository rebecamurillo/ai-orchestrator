"""run.budget_usd: make nullable so a run can be created without a budget ceiling.

When `budget_usd` is NULL the budget rule is a no-op: spend is still tracked but no park
fires, and `--max-budget-usd` is omitted from Claude argv (story 3-2, FR-17, AD-11).

Existing rows all have non-null values, so the migration applies without a backfill.
Downgrade reverts with NOT NULL — only safe when no null rows exist.

Revision ID: 0013_budget_usd_nullable
Revises: 0012_run_spend_provisional
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013_budget_usd_nullable"
down_revision: str | None = "0012_run_spend_provisional"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
COLUMN = "budget_usd"


def upgrade() -> None:
    op.alter_column(RUN, COLUMN, nullable=True)


def downgrade() -> None:
    op.alter_column(RUN, COLUMN, nullable=False)
