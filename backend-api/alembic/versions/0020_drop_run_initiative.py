"""Drop run.initiative, run.initiative_role, run.initiative_epic_id (fan-in initiative removed).

Operator decision 2026-09-30: the fan-in Initiative feature (PR #22's initiative dispatch —
`POST /api/v1/initiatives`, its preflight, view, and cancel signal) is deleted entirely; it
was built from a wrong spec and never used. These three columns, and the b-tree index on
the first of them, existed only to serve that feature — `0018_run_initiative`'s own words —
and nothing else ever read or wrote them: the fan-in **dependency** feature that survives
(`after_run_ids`, the GIN index from `0017_run_after_run_ids`, the `dependency` park) is
untouched by this revision.

The downgrade re-adds the three columns and the index exactly as `0018_run_initiative`
created them; it does not restore any data, since none of it is read by surviving code.

Revision ID: 0020_drop_run_initiative
Revises: 0019_attempt_root_shas
Create Date: 2026-09-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_drop_run_initiative"
down_revision: str | None = "0019_attempt_root_shas"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Named here so it cannot drift from the migration that created it (`0018_run_initiative`).
INDEX_NAME = "ix_run_initiative"

#: The three columns, in the order `0018_run_initiative` declared them.
COLUMNS = ("initiative", "initiative_role", "initiative_epic_id")


def upgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="run")
    for column in reversed(COLUMNS):
        op.drop_column("run", column)


def downgrade() -> None:
    for column in COLUMNS:
        op.add_column("run", sa.Column(column, sa.Text(), nullable=True))
    op.create_index(INDEX_NAME, "run", ["initiative"])
