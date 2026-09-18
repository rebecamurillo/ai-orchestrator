"""run.after_run_id FK: enforce referential integrity for the dependency column (story 5-4).

The column itself was added in 0014_run_after_run_id (story 5-3). This migration adds the
foreign-key constraint so the database refuses an after_run_id that does not name a real Run.
The constraint is deferred from 5-3 to 5-4 because 5-3's scope never writes a non-NULL value.

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
    )


def downgrade() -> None:
    op.drop_constraint("fk_run_after_run_id", "run", type_="foreignkey")
