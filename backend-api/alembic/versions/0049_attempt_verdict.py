"""attempt.verdict_*: the gate's word, frontmatter and body, stored when its row ends.

Revision ID: 0049_attempt_verdict
Revises: 0048_initiative
Create Date: 2026-11-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0049_attempt_verdict"
down_revision: str | None = "0048_initiative"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attempt", sa.Column("verdict_word", sa.Text(), nullable=True))
    op.add_column("attempt", sa.Column("verdict_fields", postgresql.JSONB(), nullable=True))
    op.add_column("attempt", sa.Column("verdict_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("attempt", "verdict_text")
    op.drop_column("attempt", "verdict_fields")
    op.drop_column("attempt", "verdict_word")
