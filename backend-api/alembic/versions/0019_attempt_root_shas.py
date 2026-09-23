"""attempt.root_start_sha, attempt.root_end_sha (hub-Run initiative workflow H4).

Spine AD-17 amendment, 2026-09-23 ("one attempt spans two trees and both are checked"):
an `agent` row declaring `with {workdir}` records its `start_sha`/`end_sha` inside the
submodule's own repository, and "the worktree root's HEAD at the same two moments" beside
them, so the hub's anchors keep being checked over agent ranges only.

Two nullable text columns in one revision, because they are one fact: an attempt either ran
in a workdir — and then it has both — or it ran at the worktree root and has neither. Every
attempt recorded before this revision is the second case, which is why no backfill runs.

No index: the pair is read back with the attempt row it belongs to and is never a filter.

Revision ID: 0019_attempt_root_shas
Revises: 0018_run_initiative
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_attempt_root_shas"
down_revision: str | None = "0018_run_initiative"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: The two columns, in the order the model declares them.
COLUMNS = ("root_start_sha", "root_end_sha")


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("attempt", sa.Column(column, sa.Text(), nullable=True))


def downgrade() -> None:
    for column in reversed(COLUMNS):
        op.drop_column("attempt", column)
