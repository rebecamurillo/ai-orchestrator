"""attempt.message and attempt.reply: what the Operator asked a senior session turn and what
it answered (AD-23).

No stored attempt is a turn, so the server default is the backfill.

Revision ID: 0027_attempt_session_text
Revises: 0026_run_senior_session
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_attempt_session_text"
down_revision: str | None = "0026_run_senior_session"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("attempt", sa.Column("message", sa.Text(), server_default="", nullable=False))
    op.add_column("attempt", sa.Column("reply", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    op.drop_column("attempt", "reply")
    op.drop_column("attempt", "message")
