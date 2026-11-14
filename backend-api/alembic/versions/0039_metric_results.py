"""metric_calculation, result_version and metric_value: immutable result versions of a Run.

Revision ID: 0039_metric_results
Revises: 0038_run_label
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0039_metric_results"
down_revision: str | None = "0038_run_label"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

CALCULATION_TABLE = "metric_calculation"
VERSION_TABLE = "result_version"
VALUE_TABLE = "metric_value"
VERSION_UNIQUE = "uq_result_version_run_n"
FIGURE_OR_WORD_CHECK = "ck_metric_value_figure_or_word"
FIGURE_OR_WORD = "value_num IS NULL OR missing IS NULL OR missing = 'partial'"
STATES = "state IN ('queued', 'running', 'failed', 'done')"
ORIGIN_TEXT = ("harness", "origin_model", "origin_repository", "branch", "commit", "base_commit")


def _empty_list() -> sa.TextClause:
    return sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.create_table(
        CALCULATION_TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("target_n", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.Text(), nullable=False, server_default="queued"),
        sa.Column("entry_point", JSONB(), nullable=False, server_default=_empty_list()),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.CheckConstraint(STATES, name=op.f("ck_metric_calculation_state")),
    )
    op.create_index("ix_metric_calculation_run_state", CALCULATION_TABLE, ["run_id", "state"])
    op.create_table(
        VERSION_TABLE,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("entry_point", JSONB(), nullable=False, server_default=_empty_list()),
        sa.Column("methods", JSONB(), nullable=False, server_default=_empty_list()),
        sa.Column("fact_set_ids", JSONB(), nullable=False, server_default=_empty_list()),
        sa.Column("toolset_fingerprint", sa.Text(), nullable=True),
        sa.UniqueConstraint("run_id", "n", name=VERSION_UNIQUE),
    )
    columns: list[sa.Column] = [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("version_id", sa.Uuid(), sa.ForeignKey(f"{VERSION_TABLE}.id"), nullable=False),
        sa.Column("metric_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("method_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope_type", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope_key", sa.Text(), nullable=False, server_default=""),
        sa.Column("scope_label", sa.Text(), nullable=True),
        sa.Column("role", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("repository", sa.Text(), nullable=True),
        sa.Column("attempt_n", sa.Integer(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("value_num", sa.Numeric(), nullable=True),
        sa.Column("unit", sa.Text(), nullable=False, server_default=""),
        sa.Column("missing", sa.Text(), nullable=True),
        sa.Column("partial_n", sa.Integer(), nullable=True),
        sa.Column("partial_m", sa.Integer(), nullable=True),
        sa.Column("carried_from", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("template_version", sa.Integer(), nullable=False, server_default="0"),
    ]
    for name in ORIGIN_TEXT:
        columns.append(sa.Column(name, sa.Text(), nullable=True))
        columns.append(sa.Column(f"{name}_na", sa.Text(), nullable=True))
    op.create_table(
        VALUE_TABLE,
        *columns,
        sa.CheckConstraint(FIGURE_OR_WORD, name=op.f(FIGURE_OR_WORD_CHECK)),
    )
    op.create_index("ix_metric_value_version", VALUE_TABLE, ["version_id"])


def downgrade() -> None:
    op.drop_table(VALUE_TABLE)
    op.drop_table(VERSION_TABLE)
    op.drop_table(CALCULATION_TABLE)
