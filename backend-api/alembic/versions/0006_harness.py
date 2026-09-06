"""harness: which coding-agent harnesses this instance may dispatch to (SPEC CAP-3, AD-10).

One row per name, no foreign key: `main.run_migrations` seeds the three names the image
installs (`claude`, `codex`, `local`) disabled, and nothing here is scoped to a Project or
a Repository.

Revision ID: 0006_harness
Revises: 0005_run
Create Date: 2026-09-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_harness"
down_revision: str | None = "0005_run"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HARNESS = "harness"


def upgrade() -> None:
    op.create_table(
        HARNESS,
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_readiness_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failing_check", sa.Text(), nullable=True),
        sa.Column("version_pin", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("name", name=op.f(f"pk_{HARNESS}")),
    )


def downgrade() -> None:
    op.drop_table(HARNESS)
