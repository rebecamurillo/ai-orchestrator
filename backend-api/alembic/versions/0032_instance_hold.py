"""instance_hold: the one row an upgrade holds the instance with (AD-30, story 4).

Revision ID: 0032_instance_hold
Revises: 0031_template_version_source
Create Date: 2026-11-11
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_instance_hold"
down_revision: str | None = "0031_template_version_source"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instance_hold",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("instance_hold")
