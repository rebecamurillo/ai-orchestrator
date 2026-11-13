"""run facts: the seven append-only tables an attempt's facts are stored in.

Revision ID: 0033_run_facts
Revises: 0032_instance_hold
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_run_facts"
down_revision: str | None = "0032_instance_hold"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

MONEY = sa.Numeric(12, 6)
TABLES = (
    "event_fact",
    "gap_fact",
    "activity_fact",
    "request_fact",
    "usage_fact",
    "gateway_read",
    "fact_set",
)


def _id() -> sa.Column[sa.Uuid]:
    return sa.Column("id", sa.Uuid(), primary_key=True)


def _fact_set_fk() -> sa.Column[sa.Uuid]:
    return sa.Column("fact_set_id", sa.Uuid(), sa.ForeignKey("fact_set.id"), nullable=False)


def upgrade() -> None:
    op.create_table(
        "fact_set",
        _id(),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("attempt.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("extractor", sa.Text(), nullable=False),
        sa.Column("extractor_version", sa.Integer(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint(
            "attempt_id",
            "extractor",
            "extractor_version",
            name="uq_fact_set_attempt_extractor_version",
        ),
    )
    op.create_index("ix_fact_set_attempt_id", "fact_set", ["attempt_id"])
    op.create_table(
        "gateway_read",
        _id(),
        sa.Column("attempt_id", sa.Uuid(), sa.ForeignKey("attempt.id"), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("rows", sa.BigInteger(), nullable=True),
        sa.Column("calls", sa.BigInteger(), nullable=True),
        sa.Column("provisional", sa.Boolean(), nullable=False),
        sa.Column("capped", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("usd", MONEY, nullable=False),
        sa.Column("prompt", sa.BigInteger(), nullable=True),
        sa.Column("completion", sa.BigInteger(), nullable=True),
    )
    op.create_index("ix_gateway_read_attempt_id", "gateway_read", ["attempt_id"])
    op.create_table(
        "usage_fact",
        _id(),
        sa.Column("fact_set_id", sa.Uuid(), sa.ForeignKey("fact_set.id"), nullable=True),
        sa.Column("gateway_read_id", sa.Uuid(), sa.ForeignKey("gateway_read.id"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("conversation", sa.Text(), nullable=True),
        sa.Column("subagent_type", sa.Text(), nullable=True),
        sa.Column("class", sa.Text(), nullable=False),
        sa.Column("tokens", sa.BigInteger(), nullable=True),
        sa.Column("usd", MONEY, nullable=True),
        sa.Column("calls", sa.BigInteger(), nullable=True),
        sa.CheckConstraint(
            "(fact_set_id IS NULL) <> (gateway_read_id IS NULL)",
            name=op.f("ck_usage_fact_one_parent"),
        ),
    )
    op.create_index("ix_usage_fact_fact_set_id", "usage_fact", ["fact_set_id"])
    op.create_index("ix_usage_fact_gateway_read_id", "usage_fact", ["gateway_read_id"])
    op.create_table(
        "request_fact",
        _id(),
        _fact_set_fk(),
        sa.Column("message_id", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("conversation", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_uncached", sa.BigInteger(), nullable=False),
        sa.Column("cache_read", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_5m", sa.BigInteger(), nullable=False),
        sa.Column("cache_write_1h", sa.BigInteger(), nullable=False),
        sa.Column("output", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_request_fact_fact_set_id", "request_fact", ["fact_set_id"])
    op.create_table(
        "activity_fact",
        _id(),
        _fact_set_fk(),
        sa.Column("conversation", sa.Text(), nullable=False),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("calls", sa.BigInteger(), nullable=False),
        sa.Column("errors", sa.BigInteger(), nullable=False),
        sa.Column("files_read", sa.BigInteger(), nullable=False),
        sa.Column("files_edited", sa.BigInteger(), nullable=False),
        sa.Column("test_runs", sa.BigInteger(), nullable=False),
        sa.Column("messages", sa.BigInteger(), nullable=False),
    )
    op.create_index("ix_activity_fact_fact_set_id", "activity_fact", ["fact_set_id"])
    op.create_table(
        "gap_fact",
        _id(),
        _fact_set_fk(),
        sa.Column("conversation", sa.Text(), nullable=False),
        sa.Column("messages", sa.BigInteger(), nullable=False),
        sa.Column("first_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("gaps_s", sa.ARRAY(sa.Integer()), nullable=False),
    )
    op.create_index("ix_gap_fact_fact_set_id", "gap_fact", ["fact_set_id"])
    op.create_table(
        "event_fact",
        _id(),
        _fact_set_fk(),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conversation", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("command", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
    )
    op.create_index("ix_event_fact_fact_set_id", "event_fact", ["fact_set_id"])


def downgrade() -> None:
    for table in TABLES:
        op.drop_table(table)
