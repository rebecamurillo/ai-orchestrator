"""run_repository and run_commit: per-repository records and the commits the orchestrator made.

Revision ID: 0037_run_repository_records
Revises: 0036_step_run_role
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0037_run_repository_records"
down_revision: str | None = "0036_step_run_role"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "run_repository",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("remote_url", sa.Text(), nullable=False),
        sa.Column("base_branch", sa.Text(), nullable=False),
        sa.Column("branch", sa.Text(), nullable=False),
        sa.Column("base_tip", sa.Text(), nullable=False),
        sa.Column("head_pushed", sa.Text(), nullable=True),
        sa.Column("head_local_at_end", sa.Text(), nullable=True),
        sa.UniqueConstraint("run_id", "path", name="uq_run_repository_run_path"),
    )
    op.create_table(
        "run_commit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("run.id"), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("sha", sa.Text(), nullable=False),
        sa.Column("made_by", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "path", "sha", name="uq_run_commit_run_path_sha"),
        sa.CheckConstraint(
            "made_by IN ('wip', 'prepare', 'git.commit', 'git.merge', 'session', 'operator_edit')",
            name=op.f("ck_run_commit_made_by"),
        ),
    )


def downgrade() -> None:
    op.drop_table("run_commit")
    op.drop_table("run_repository")
