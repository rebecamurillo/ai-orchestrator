"""run.spend_provisional: whether any attempt in the run's spend sum was provisional.

Tracks the provisional flag alongside spend_usd, set by record_attempt_spend. Defaults to
FALSE so all pre-migration rows read correctly without a backfill.
Chains from `0011_last_opened_before` (the current head migration).

Revision ID: 0012_run_spend_provisional
Revises: 0011_last_opened_before
Create Date: 2026-09-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_run_spend_provisional"
down_revision: str | None = "0011_last_opened_before"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
COLUMN = "spend_provisional"


def upgrade() -> None:
    op.add_column(
        RUN,
        sa.Column(COLUMN, sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
    )


def downgrade() -> None:
    op.drop_column(RUN, COLUMN)
