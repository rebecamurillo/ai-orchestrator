"""run.after_run_id: add FK constraint to run.id (story 5-4).

The column was added in 0014 as a bare UUID column (no FK) so the field could be
cleared by the `start` signal without a dependency violation. Story 5-4 adds the FK
with `ondelete="SET NULL"` and `deferrable=True / initially="DEFERRED"` so that a Run
and its dependents can be written in the same transaction (the predecessor is inserted
first, referential integrity is checked only at commit time).

Revision ID: 0015_run_after_run_id_fk
Revises: 0014_run_after_run_id
Create Date: 2026-09-18
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0015_run_after_run_id_fk"
down_revision: str | None = "0014_run_after_run_id"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_foreign_key(
        "fk_run_after_run_id",
        "run",
        "run",
        ["after_run_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint("fk_run_after_run_id", "run", type_="foreignkey")
