"""initiative, initiative_advance, and the initiative keys on run (AD-36).

Revision ID: 0048_initiative
Revises: 0047_project_package
Create Date: 2026-11-24
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0048_initiative"
down_revision: str | None = "0047_project_package"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "initiative",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("repository_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("first_message", sa.Text(), nullable=False),
        sa.Column("sequence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("round", sa.Integer(), server_default="1", nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("branch_cleanup_error", sa.Text(), nullable=True),
        sa.Column("pr_merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_initiative")),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_initiative_project_id_project")
        ),
        sa.ForeignKeyConstraint(
            ["repository_id"],
            ["repository.id"],
            name=op.f("fk_initiative_repository_id_repository"),
        ),
    )
    op.create_index(
        "uq_initiative_repository_slug_open",
        "initiative",
        ["repository_id", "slug"],
        unique=True,
        postgresql_where=sa.text("cancelled_at IS NULL"),
    )
    op.add_column("run", sa.Column("initiative_id", sa.Uuid(), nullable=True))
    op.add_column("run", sa.Column("initiative_round", sa.Integer(), nullable=True))
    op.add_column("run", sa.Column("initiative_position", sa.Integer(), nullable=True))
    op.create_foreign_key(
        op.f("fk_run_initiative_id_initiative"),
        "run",
        "initiative",
        ["initiative_id"],
        ["id"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_check_constraint(
        op.f("ck_run_initiative_keys_together"),
        "run",
        "(initiative_id IS NULL AND initiative_round IS NULL AND initiative_position IS NULL)"
        " OR (initiative_id IS NOT NULL AND initiative_round IS NOT NULL"
        " AND initiative_position IS NOT NULL)",
    )
    op.create_index(
        "uq_run_initiative_key",
        "run",
        ["initiative_id", "initiative_round", "initiative_position"],
        unique=True,
        postgresql_where=sa.text("initiative_id IS NOT NULL"),
    )
    op.create_table(
        "initiative_advance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("initiative_id", sa.Uuid(), nullable=False),
        sa.Column("from_run_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("blocked_reason", sa.Text(), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_initiative_advance")),
        sa.ForeignKeyConstraint(
            ["initiative_id"],
            ["initiative.id"],
            name=op.f("fk_initiative_advance_initiative_id_initiative"),
        ),
        sa.ForeignKeyConstraint(
            ["from_run_id"], ["run.id"], name=op.f("fk_initiative_advance_from_run_id_run")
        ),
        sa.UniqueConstraint(
            "initiative_id",
            "round",
            "position",
            name=op.f("uq_initiative_advance_initiative_id_round_position"),
        ),
    )


def downgrade() -> None:
    op.drop_table("initiative_advance")
    op.drop_index("uq_run_initiative_key", table_name="run")
    op.drop_constraint(op.f("ck_run_initiative_keys_together"), "run", type_="check")
    op.drop_constraint(op.f("fk_run_initiative_id_initiative"), "run", type_="foreignkey")
    op.drop_column("run", "initiative_position")
    op.drop_column("run", "initiative_round")
    op.drop_column("run", "initiative_id")
    op.drop_index("uq_initiative_repository_slug_open", table_name="initiative")
    op.drop_table("initiative")
