"""harness readiness: one Run's evaluation, written onto the harness it evaluated
(SPEC CAP-8, AD-10).

`last_readiness_run_id`/`lines` are what `evaluate` writes alongside the
`enabled`/`last_readiness_at`/`failing_check` columns story 4-3 already created. Nullable
and defaulted so every harness row seeded before this story ever ran an evaluation reads
back unchanged: `last_readiness_run_id` starts `NULL`, `lines` starts `'[]'`.

The seeded `readiness` Project (SPEC CAP-8) needs no migration of its own: `Project.builtin`
is derived from `slug` alone, not a stored column — see `infrastructure/db/repositories/
projects.py::to_entity`'s own docstring for why (`tests/unit/test_project_repository_
adapter.py::test_the_table_carries_exactly_the_columns_the_entity_has` closes the `project`
table's column set, and names no successor story).

Revision ID: 0008_harness_readiness
Revises: 0007_run_gc
Create Date: 2026-09-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_harness_readiness"
down_revision: str | None = "0007_run_gc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HARNESS = "harness"


def upgrade() -> None:
    op.add_column(HARNESS, sa.Column("last_readiness_run_id", sa.Uuid(), nullable=True))
    op.add_column(
        HARNESS,
        sa.Column(
            "lines",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column(HARNESS, "lines")
    op.drop_column(HARNESS, "last_readiness_run_id")
