"""template, template_version: stored Templates and their immutable numbered versions.

`template` is one row per name, holding the latest version's parsed description so
`GET /templates` never re-parses YAML to answer a list. `template_version` is one row per
`(name, version)`, unique on that pair, with a foreign key to its `template` row; nothing in
this system ever updates or deletes one (AD-15) — `calls` is `jsonb`, the callee list pinned
when that version was saved.

Revision ID: 0004_template
Revises: 0003_repository
Create Date: 2026-09-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_template"
down_revision: str | None = "0003_repository"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "template"
VERSION_TABLE = "template_version"
NAME_VERSION_INDEX = "ix_template_version_name_version"


def upgrade() -> None:
    """Create `template` and `template_version`, with the version's scoped unique index."""
    op.create_table(
        TABLE,
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f(f"pk_{TABLE}")),
    )
    op.create_table(
        VERSION_TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("yaml", sa.Text(), nullable=False),
        sa.Column("hash", sa.Text(), nullable=False),
        sa.Column("calls", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["name"],
            [f"{TABLE}.name"],
            name=op.f(f"fk_{VERSION_TABLE}_name_{TABLE}"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{VERSION_TABLE}")),
    )
    op.create_index(op.f(NAME_VERSION_INDEX), VERSION_TABLE, ["name", "version"], unique=True)


def downgrade() -> None:
    """Drop both tables, `template_version` first for its foreign key to `template`."""
    op.drop_index(op.f(NAME_VERSION_INDEX), table_name=VERSION_TABLE)
    op.drop_table(VERSION_TABLE)
    op.drop_table(TABLE)
