"""repository: one row per git repository a Run works in, nested under its Project.

`test_globs` and `clone_check` are `jsonb`: short, ordered or single-object, always read
whole with the Repository, never queried into. `project_id` carries a foreign key to
`project` — a Repository without a Project is meaningless — and the unique index on
`(project_id, url)` is the guarantee behind the use case's duplicate-url conflict: two
concurrent creates would both pass that check, and the index is what stops the second from
landing.

Revision ID: 0003_repository
Revises: 0002_project
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_repository"
down_revision: str | None = "0002_project"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "repository"
PARENT_TABLE = "project"
PROJECT_URL_INDEX = "ix_repository_project_id_url"
PROJECT_SLUG_INDEX = "ix_repository_project_id_slug"


def upgrade() -> None:
    """Create `repository`, with its foreign key to `project` and the scoped unique index."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.Text(), nullable=False),
        sa.Column("install_command", sa.Text(), nullable=False),
        sa.Column("quality_gate_command", sa.Text(), nullable=False),
        sa.Column("unit_test_command", sa.Text(), nullable=False),
        sa.Column("test_globs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("package_manager", sa.Text(), nullable=False),
        sa.Column("clone_check", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"],
            [f"{PARENT_TABLE}.id"],
            name=op.f(f"fk_{TABLE}_project_id_{PARENT_TABLE}"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
    )
    op.create_index(op.f(PROJECT_URL_INDEX), TABLE, ["project_id", "url"], unique=True)
    op.create_index(op.f(PROJECT_SLUG_INDEX), TABLE, ["project_id", "slug"], unique=True)


def downgrade() -> None:
    """Drop the table and, with it, its foreign key and its two unique indexes."""
    op.drop_index(op.f(PROJECT_SLUG_INDEX), table_name=TABLE)
    op.drop_index(op.f(PROJECT_URL_INDEX), table_name=TABLE)
    op.drop_table(TABLE)
