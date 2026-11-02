"""chat_thread and chat_notice: a stop's chat thread, and the claim on a senior-accept notice
(AD-25, story 3-3).

`chat_thread` is unique per `(run_id, park_seq)` and per `ref`, the two keys `chat_poll`'s
claim relies on when fires overlap. `chat_notice` is keyed by its `senior_accept` gate
record. Both go with their Run. The upgrade writes no row.

Revision ID: 0029_chat_thread
Revises: 0028_project_channel
Create Date: 2026-11-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0029_chat_thread"
down_revision: str | None = "0028_project_channel"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

THREAD_TABLE = "chat_thread"
NOTICE_TABLE = "chat_notice"
RUN_TABLE = "run"
GATE_RECORD_TABLE = "gate_record"


def upgrade() -> None:
    op.create_table(
        THREAD_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("park_seq", sa.Integer(), nullable=False),
        sa.Column("park_kind", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=True),
        sa.Column("cursor", sa.Text(), nullable=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("last_reminded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('posting', 'open', 'closed', 'failed')",
            name=op.f(f"ck_{THREAD_TABLE}_state"),
        ),
        sa.CheckConstraint(
            "provider IN ('mattermost', 'slack')", name=op.f(f"ck_{THREAD_TABLE}_provider")
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{RUN_TABLE}.id"],
            name=op.f(f"fk_{THREAD_TABLE}_run_id_{RUN_TABLE}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{THREAD_TABLE}")),
        sa.UniqueConstraint("run_id", "park_seq", name=op.f(f"uq_{THREAD_TABLE}_run_id_park_seq")),
        sa.UniqueConstraint("ref", name=op.f(f"uq_{THREAD_TABLE}_ref")),
    )
    op.create_table(
        NOTICE_TABLE,
        sa.Column("gate_record_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["gate_record_id"],
            [f"{GATE_RECORD_TABLE}.id"],
            name=op.f(f"fk_{NOTICE_TABLE}_gate_record_id_{GATE_RECORD_TABLE}"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{RUN_TABLE}.id"],
            name=op.f(f"fk_{NOTICE_TABLE}_run_id_{RUN_TABLE}"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("gate_record_id", name=op.f(f"pk_{NOTICE_TABLE}")),
    )


def downgrade() -> None:
    op.drop_table(NOTICE_TABLE)
    op.drop_table(THREAD_TABLE)
