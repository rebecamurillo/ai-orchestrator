"""project_channel: one Project's chat channel, its bot token Fernet-encrypted (AD-25, AD-5).

No row means `off`, so the upgrade writes none and every existing Project reads `off`. The
row is removed with its Project (`ON DELETE CASCADE`).

Revision ID: 0028_project_channel
Revises: 0027_attempt_session_text
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_project_channel"
down_revision: str | None = "0027_attempt_session_text"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE = "project_channel"
PARENT_TABLE = "project"


def upgrade() -> None:
    op.create_table(
        TABLE,
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("token_enc", sa.Text(), nullable=False),
        sa.Column("allowed_users", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata_only", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "provider IN ('mattermost', 'slack')", name=op.f(f"ck_{TABLE}_provider")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            [f"{PARENT_TABLE}.id"],
            name=op.f(f"fk_{TABLE}_project_id_{PARENT_TABLE}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", name=op.f(f"pk_{TABLE}")),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
