"""step_run.role: the role the Template step declared, written at plan time.

Revision ID: 0036_step_run_role
Revises: 0035_migrated_attempt_facts
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0036_step_run_role"
down_revision: str | None = "0035_migrated_attempt_facts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("step_run", sa.Column("role", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("step_run", "role")
