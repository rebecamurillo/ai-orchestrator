"""run.partition_branch: the declared branch used to partition the queue slot (AD-12, story 5-1).

Stores the branch-keyed partition so pre-flight, queue-reason logic, and the git.worktree
executor backstop can compare branches without re-reading step_run rows. NULL for Runs
created before this migration — those are treated as non-competing.
Chains from `0012_run_spend_provisional` (the current head migration).

Revision ID: 0013_run_partition_branch
Revises: 0012_run_spend_provisional
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_run_partition_branch"
down_revision: str | None = "0013_budget_usd_nullable"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run", sa.Column("partition_branch", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("run", "partition_branch")
