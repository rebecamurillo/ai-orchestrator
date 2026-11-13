"""fact_set.subscription: whether the attempt ran on the Claude subscription (no backfill).

Revision ID: 0040_fact_set_subscription
Revises: 0039_metric_results
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0040_fact_set_subscription"
down_revision: str | None = "0039_metric_results"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("fact_set", sa.Column("subscription", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("fact_set", "subscription")
