"""chat_thread close columns: when a thread closed, its closing notice, and its one late
mention notice (AD-25, story 4-2).

Six nullable columns and four named CHECKs: the two notice alphabets (a mention notice never
takes `due`), a closing notice only on a `closed` thread, and a mention notice only after a
posted closing notice. The upgrade writes no data, so a thread closed before it keeps
`closed_at` NULL and gets neither notice.

Revision ID: 0030_chat_thread_close
Revises: 0029_chat_thread
Create Date: 2026-11-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_chat_thread_close"
down_revision: str | None = "0029_chat_thread"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

TABLE = "chat_thread"
COLUMNS = (
    ("closed_at", sa.DateTime(timezone=True)),
    ("close_notice", sa.Text()),
    ("close_notice_at", sa.DateTime(timezone=True)),
    ("mention_notice", sa.Text()),
    ("mention_notice_at", sa.DateTime(timezone=True)),
    ("mention_cursor", sa.Text()),
)
CHECKS = {
    "close_notice": "close_notice IN ('due', 'sending', 'posted', 'failed')",
    "mention_notice": "mention_notice IN ('sending', 'posted', 'failed')",
    "close_notice_closed": "close_notice IS NULL OR state = 'closed'",
    "mention_notice_after_close": "mention_notice IS NULL OR close_notice = 'posted'",
}


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column(TABLE, sa.Column(name, kind, nullable=True))
    for name, text in CHECKS.items():
        op.create_check_constraint(op.f(f"ck_{TABLE}_{name}"), TABLE, text)


def downgrade() -> None:
    for name in reversed(CHECKS):
        op.drop_constraint(op.f(f"ck_{TABLE}_{name}"), TABLE, type_="check")
    for name, _ in reversed(COLUMNS):
        op.drop_column(TABLE, name)
