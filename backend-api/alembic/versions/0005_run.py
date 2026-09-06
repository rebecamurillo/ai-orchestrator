"""run, step_run, attempt, gate_record: a Run, its planned rows, their attempts, its record.

Four tables, in the order the foreign keys need them: `run` hangs off `project` and
`repository`, `step_run` off `run`, `attempt` off both `run` and `step_run`, `gate_record`
off `run`. Every list and map is `jsonb` — short, always read whole with its row, never
queried into — money is `numeric(12, 6)` and the manual estimate `numeric(10, 2)`.

Three unique indexes carry a rule rather than a read: `(run_id, seq)` and `(run_id, path)`
are what make a plan a list rather than a bag, and `(step_run_id, n)` is what stops a restart
from writing a second attempt at the same number. The other four are reads — the Board's
project filter, the queue's status filter, the preflight rule's `(repository, status)`, and
the Run screen's gate record in the order things happened.

Revision ID: 0005_run
Revises: 0004_template
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_run"
down_revision: str | None = "0004_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN = "run"
STEP_RUN = "step_run"
ATTEMPT = "attempt"
GATE_RECORD = "gate_record"
PROJECT = "project"
REPOSITORY = "repository"

RUN_PROJECT_INDEX = "ix_run_project_id"
RUN_STATUS_INDEX = "ix_run_status"
RUN_REPOSITORY_STATUS_INDEX = "ix_run_repository_id_status"
STEP_RUN_SEQ_INDEX = "ix_step_run_run_id_seq"
STEP_RUN_PATH_INDEX = "ix_step_run_run_id_path"
ATTEMPT_N_INDEX = "ix_attempt_step_run_id_n"
GATE_RECORD_AT_INDEX = "ix_gate_record_run_id_at"

MONEY = sa.Numeric(12, 6)
HOURS = sa.Numeric(10, 2)


def _jsonb() -> postgresql.JSONB:
    return postgresql.JSONB(astext_type=sa.Text())


def _create_run() -> None:
    op.create_table(
        RUN,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("template_name", sa.Text(), nullable=False),
        sa.Column("template_version", sa.Integer(), nullable=False),
        sa.Column("pinned_versions", _jsonb(), nullable=False),
        sa.Column("inputs", _jsonb(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan_ref", sa.Text(), nullable=True),
        sa.Column("plan_refs", _jsonb(), nullable=False),
        sa.Column("engine_ref", _jsonb(), nullable=False),
        sa.Column("budget_usd", MONEY, nullable=False),
        sa.Column("spend_usd", MONEY, nullable=False),
        sa.Column("manual_estimate_h", HOURS, nullable=True),
        sa.Column("re_review_done", sa.Boolean(), nullable=False),
        sa.Column("park_kind", sa.Text(), nullable=True),
        sa.Column("park_path", sa.Text(), nullable=True),
        sa.Column("park_reason", sa.Text(), nullable=True),
        sa.Column("accepted_paths", _jsonb(), nullable=False),
        sa.Column("worktree_path", sa.Text(), nullable=True),
        sa.Column("worktrees", _jsonb(), nullable=False),
        sa.Column("compare_urls", _jsonb(), nullable=False),
        sa.Column("trace_id", sa.Text(), nullable=True),
        sa.Column("terminal_session", sa.Boolean(), nullable=False),
        sa.Column("active_seconds", sa.Integer(), nullable=False),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], [f"{PROJECT}.id"], name=op.f(f"fk_{RUN}_project_id_{PROJECT}")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            [f"{REPOSITORY}.id"],
            name=op.f(f"fk_{RUN}_repository_id_{REPOSITORY}"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{RUN}")),
    )
    op.create_index(op.f(RUN_PROJECT_INDEX), RUN, ["project_id"], unique=False)
    op.create_index(op.f(RUN_STATUS_INDEX), RUN, ["status"], unique=False)
    op.create_index(
        op.f(RUN_REPOSITORY_STATUS_INDEX), RUN, ["repository_id", "status"], unique=False
    )


def _create_step_run() -> None:
    op.create_table(
        STEP_RUN,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("gate", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("with_resolved", _jsonb(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("redispatch_count", sa.Integer(), nullable=False),
        sa.Column("frame", sa.Text(), nullable=True),
        sa.Column("story_id", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{RUN}.id"], name=op.f(f"fk_{STEP_RUN}_run_id_{RUN}")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{STEP_RUN}")),
    )
    op.create_index(op.f(STEP_RUN_SEQ_INDEX), STEP_RUN, ["run_id", "seq"], unique=True)
    op.create_index(op.f(STEP_RUN_PATH_INDEX), STEP_RUN, ["run_id", "path"], unique=True)


def _create_attempt() -> None:
    op.create_table(
        ATTEMPT,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("step_run_id", sa.Uuid(), nullable=False),
        sa.Column("n", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("engine_ref", _jsonb(), nullable=False),
        sa.Column("start_sha", sa.Text(), nullable=True),
        sa.Column("end_sha", sa.Text(), nullable=True),
        sa.Column("frozen_test_files", _jsonb(), nullable=True),
        sa.Column("log_path", sa.Text(), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("output_ref", sa.Text(), nullable=True),
        sa.Column("harness", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=True),
        sa.Column("pgid", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost_usd", MONEY, nullable=True),
        sa.Column("cost_provisional", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], [f"{RUN}.id"], name=op.f(f"fk_{ATTEMPT}_run_id_{RUN}")),
        sa.ForeignKeyConstraint(
            ["step_run_id"],
            [f"{STEP_RUN}.id"],
            name=op.f(f"fk_{ATTEMPT}_step_run_id_{STEP_RUN}"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{ATTEMPT}")),
    )
    op.create_index(op.f(ATTEMPT_N_INDEX), ATTEMPT, ["step_run_id", "n"], unique=True)


def _create_gate_record() -> None:
    op.create_table(
        GATE_RECORD,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("attempt_n", sa.Integer(), nullable=True),
        sa.Column("payload", _jsonb(), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], [f"{RUN}.id"], name=op.f(f"fk_{GATE_RECORD}_run_id_{RUN}")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{GATE_RECORD}")),
    )
    op.create_index(op.f(GATE_RECORD_AT_INDEX), GATE_RECORD, ["run_id", "at"], unique=False)


def upgrade() -> None:
    """Create the four tables, parents before the children that reference them."""
    _create_run()
    _create_step_run()
    _create_attempt()
    _create_gate_record()


def downgrade() -> None:
    """Drop them in reverse, children before the parents they reference."""
    op.drop_index(op.f(GATE_RECORD_AT_INDEX), table_name=GATE_RECORD)
    op.drop_table(GATE_RECORD)
    op.drop_index(op.f(ATTEMPT_N_INDEX), table_name=ATTEMPT)
    op.drop_table(ATTEMPT)
    op.drop_index(op.f(STEP_RUN_PATH_INDEX), table_name=STEP_RUN)
    op.drop_index(op.f(STEP_RUN_SEQ_INDEX), table_name=STEP_RUN)
    op.drop_table(STEP_RUN)
    op.drop_index(op.f(RUN_REPOSITORY_STATUS_INDEX), table_name=RUN)
    op.drop_index(op.f(RUN_STATUS_INDEX), table_name=RUN)
    op.drop_index(op.f(RUN_PROJECT_INDEX), table_name=RUN)
    op.drop_table(RUN)
