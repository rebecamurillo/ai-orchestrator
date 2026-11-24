"""repository.initiative_folder: where every initiative of the repository lives.

Revision ID: 0046_repository_initiative_folder
Revises: 0045_project_run_defaults
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0046_repository_initiative_folder"
down_revision: str | None = "0045_project_run_defaults"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "repository",
        sa.Column("initiative_folder", sa.Text(), nullable=False, server_default="initiatives"),
    )


def downgrade() -> None:
    op.drop_column("repository", "initiative_folder")
