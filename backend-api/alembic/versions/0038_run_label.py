"""run label: a readable name for every Run, with the default written for existing ones.

Revision ID: 0038_run_label
Revises: 0037_run_repository_records
Create Date: 2026-11-13
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op

from orchestrator.application.rules.run_label import default_label

revision: str = "0038_run_label"
down_revision: str | None = "0037_run_repository_records"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_run = sa.table(
    "run",
    sa.column("id", sa.Uuid()),
    sa.column("project_id", sa.Uuid()),
    sa.column("inputs", sa.JSON()),
    sa.column("template_name", sa.Text()),
    sa.column("created_at", sa.DateTime(timezone=True)),
    sa.column("label", sa.Text()),
)
_project = sa.table("project", sa.column("id", sa.Uuid()), sa.column("name", sa.Text()))


def labels_of(rows: Iterable[Mapping[str, Any]]) -> dict[UUID, str]:
    """The default label of each stored Run, by the rule `create_run` uses."""
    return {
        row["id"]: default_label(
            row["name"] or "", row["inputs"] or {}, row["template_name"], row["created_at"]
        )
        for row in rows
    }


def upgrade() -> None:
    op.add_column("run", sa.Column("label", sa.Text(), nullable=False, server_default=""))
    op.add_column(
        "run",
        sa.Column("label_set_by_operator", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    conn = op.get_bind()
    rows = (
        conn.execute(
            sa.select(
                _run.c.id, _run.c.inputs, _run.c.template_name, _run.c.created_at, _project.c.name
            ).select_from(_run.outerjoin(_project, _project.c.id == _run.c.project_id))
        )
        .mappings()
        .all()
    )
    for run_id, label in labels_of(rows).items():
        conn.execute(sa.update(_run).where(_run.c.id == run_id).values(label=label))


def downgrade() -> None:
    op.drop_column("run", "label_set_by_operator")
    op.drop_column("run", "label")
