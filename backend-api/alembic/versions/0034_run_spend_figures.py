"""run spend figures: gateway, harness and gate totals with their reported flags.

Revision ID: 0034_run_spend_figures
Revises: 0033_run_facts
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_run_spend_figures"
down_revision: str | None = "0033_run_facts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

MONEY = sa.Numeric(12, 6)
MONEY_COLUMNS = ("gateway_spend_usd", "harness_spend_usd", "gate_spend_usd")
FLAG_COLUMNS = ("gateway_reported", "harness_reported")


def upgrade() -> None:
    for name in MONEY_COLUMNS:
        op.add_column("run", sa.Column(name, MONEY, nullable=False, server_default="0"))
    for name in FLAG_COLUMNS:
        op.add_column(
            "run", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    for name in reversed(FLAG_COLUMNS + MONEY_COLUMNS):
        op.drop_column("run", name)
