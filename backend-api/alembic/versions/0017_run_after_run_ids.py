"""run.after_run_ids: the 1:1 dependency pointer becomes a fan-in list (multi-repo S1).

Spine AD-12/AD-13 amendment, 2026-09-23: `after_run_ids` is a fan-in list, so a Run may
wait for several predecessors and an initiative's DAG is readable from the Runs themselves.

Three steps, in one revision so the table is never half-migrated:

1. add `after_run_ids uuid[] NOT NULL DEFAULT '{}'` — an array rather than `jsonb`, unlike
   every other list on this table, because this one is queried into (`list_dependents`);
2. backfill `ARRAY[after_run_id]` wherever the old column is non-null;
3. drop the old column, and with it the deferred self-FK 0016 added — Postgres arrays
   cannot carry a foreign key, which is why `resolve_dependent` now decides for itself
   what a dangling predecessor id means.

A GIN index lands with the column: the only query is `after_run_ids @> ARRAY[:id]`, and no
b-tree answers array containment.

The downgrade is faithful: it restores the nullable `uuid` column, copies back the first
element of each list (the only value the old shape could hold), restores the FK, and drops
the array and its index. A Run that had fanned in on more than one predecessor loses the
extra edges, because the old column has nowhere to put them.

Revision ID: 0017_run_after_run_ids
Revises: 0016_run_after_run_id_fk
Create Date: 2026-09-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0017_run_after_run_ids"
down_revision: str | None = "0016_run_after_run_id_fk"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

#: Named here so the model (`RUN_AFTER_RUN_IDS_INDEX`) and the migration cannot drift.
INDEX_NAME = "ix_run_after_run_ids"
FK_NAME = "fk_run_after_run_id"


def upgrade() -> None:
    op.add_column(
        "run",
        sa.Column(
            "after_run_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
    )
    op.execute(
        sa.text("UPDATE run SET after_run_ids = ARRAY[after_run_id] WHERE after_run_id IS NOT NULL")
    )
    op.drop_constraint(FK_NAME, "run", type_="foreignkey")
    op.drop_column("run", "after_run_id")
    op.create_index(INDEX_NAME, "run", ["after_run_ids"], postgresql_using="gin")


def downgrade() -> None:
    op.add_column("run", sa.Column("after_run_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute(
        sa.text(
            "UPDATE run SET after_run_id = after_run_ids[1] "
            "WHERE array_length(after_run_ids, 1) IS NOT NULL"
        )
    )
    op.create_foreign_key(
        FK_NAME,
        "run",
        "run",
        ["after_run_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )
    op.drop_index(INDEX_NAME, table_name="run")
    op.drop_column("run", "after_run_ids")
