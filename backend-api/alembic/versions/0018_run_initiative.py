"""run.initiative, run.initiative_role, run.initiative_epic_id (multi-repo S6).

Spine AD-12 amendment, 2026-09-23 ("Initiative dispatch"): "Each Run stores `initiative`
and `initiative_role`; the templates the dispatch instantiates are request inputs (AD-7), so
the role is what the machine reads, never a template name."

Three nullable text columns in one revision, because they are one fact: a Run either belongs
to an initiative — and then it has a slug, a role and (for the epic and merge Runs) the
`epics.yaml` entry it came from — or it belongs to none and all three are `NULL`. A Run
created before this revision is exactly the second case, which is why no backfill runs.

The b-tree index is on `initiative` alone: the only query is `GET /initiatives/{slug}`'s
"every member Run of this slug", and the role is a column that read renders rather than
filters on.

Revision ID: 0018_run_initiative
Revises: 0017_run_after_run_ids
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_run_initiative"
down_revision: str | None = "0017_run_after_run_ids"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Named here so the model (`RUN_INITIATIVE_INDEX`) and the migration cannot drift.
INDEX_NAME = "ix_run_initiative"

#: The three columns, in the order the model declares them.
COLUMNS = ("initiative", "initiative_role", "initiative_epic_id")


def upgrade() -> None:
    for column in COLUMNS:
        op.add_column("run", sa.Column(column, sa.Text(), nullable=True))
    op.create_index(INDEX_NAME, "run", ["initiative"])


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="run")
    for column in reversed(COLUMNS):
        op.drop_column("run", column)
