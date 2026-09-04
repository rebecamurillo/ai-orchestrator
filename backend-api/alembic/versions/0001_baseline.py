"""baseline: schema public, no tables

The empty schema is the correct starting point. No domain entity exists yet — a Project, a
Repository, a Run, a Template all arrive with the story that needs them, each with its own
revision. What this revision establishes is the chain itself: `alembic_version` exists in
schema `public`, holds this id, and every later revision has a parent to hang from.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-09-03
"""

from __future__ import annotations

from collections.abc import Sequence

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create nothing. The chain, not a table, is what this revision adds."""


def downgrade() -> None:
    """There is nothing before the baseline to go back to."""
