"""project_package: the package a Project installed from its hub; template_version.package_sha.

Revision ID: 0047_project_package
Revises: 0046_repository_init_folder
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0047_project_package"
down_revision: str | None = "0046_repository_init_folder"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_package",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("ref", sa.Text(), nullable=False),
        sa.Column("sha", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("declaration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_package")),
        sa.UniqueConstraint("project_id", name=op.f("uq_project_package_project_id")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_project_package_project_id_project")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repository.id"],
            name=op.f("fk_project_package_repository_id_repository"),
        ),
    )
    op.add_column("template_version", sa.Column("package_sha", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("template_version", "package_sha")
    op.drop_table("project_package")
