"""project: the Project entity and its encrypted environment variables

The first table this system owns. `name` and `slug` are uniquely indexed because both
identify a Project to a human — the name on the Board, the slug in `/work/{project}/…`
(AD-14) — and a use-case check alone would let two concurrent creates through. The index
refuses the second write; turning that refusal into a 409 rather than a 500 is not
implemented in this story, so a lost race is reported as an internal error.

`context_paths` and `env_vars_enc` are `jsonb`: short, ordered, always read whole with the
Project, never queried into. `env_vars_enc` holds `[{name, value_enc}]`, the value a Fernet
token under `ORCHESTRATOR_SECRET_KEY` (AD-5); no plaintext value reaches this table.

Revision ID: 0002_project
Revises: 0001_baseline
Create Date: 2026-09-04
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_project"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "project"


def upgrade() -> None:
    """Create `project`, with the two unique indexes the identity of a Project needs."""
    op.create_table(
        TABLE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("context_text", sa.Text(), nullable=False),
        sa.Column("context_paths", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("env_vars_enc", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("log_prompt_content", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
    )
    op.create_index(op.f("ix_project_name"), TABLE, ["name"], unique=True)
    op.create_index(op.f("ix_project_slug"), TABLE, ["slug"], unique=True)


def downgrade() -> None:
    """Drop the table and, with it, both of its indexes."""
    op.drop_index(op.f("ix_project_slug"), table_name=TABLE)
    op.drop_index(op.f("ix_project_name"), table_name=TABLE)
    op.drop_table(TABLE)
