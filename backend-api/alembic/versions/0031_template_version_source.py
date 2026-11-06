"""template_version.source: where a stored version's text came from (AD-26, story 4).

One nullable column: `shipped` (the image's set), `saved` (the web editor) or `folder` (the
operator's folder). The upgrade writes no data, so a row stored before it keeps `source`
NULL and is never reported as coming from the folder.

Revision ID: 0031_template_version_source
Revises: 0030_chat_thread_close
Create Date: 2026-11-06
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_template_version_source"
down_revision: str | None = "0030_chat_thread_close"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("template_version", sa.Column("source", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("template_version", "source")
