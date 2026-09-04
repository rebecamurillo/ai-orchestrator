"""The `repository` table: one row per git repository a Run works in, nested under Project.

`test_globs` and `clone_check` are `jsonb`, not child tables — both are short, always read
whole with the Repository, and never queried into. `clone_check` is written by exactly one
later use case (`run_clone_check`, 2.3); every row this story creates holds its pending
shape.

`project_id` carries a real foreign key, unlike `context_paths`/`env_vars_enc` on `project`:
a Repository is meaningless without the Project it is nested under. The unique index on
`(project_id, url)` is the guarantee behind the use case's duplicate-url `Conflict` — two
concurrent creates would both pass that check, and the index is what stops the second from
landing. `(project_id, slug)` is unique for the same reason: `_free_repo_slug` is a
read-then-write over the same table, and only the index — not the use-case scan — stops two
concurrent creates from landing the same slug under one Project.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.project import ProjectRow

TABLE_NAME = "repository"

#: The unique index behind the use case's scoped duplicate-`url` conflict.
PROJECT_URL_INDEX = "ix_repository_project_id_url"

#: The unique index behind `_free_repo_slug`'s read-then-write guarantee.
PROJECT_SLUG_INDEX = "ix_repository_project_id_slug"


class RepositoryRow(Base):
    """One stored Repository."""

    __tablename__ = TABLE_NAME
    __table_args__ = (
        Index(PROJECT_URL_INDEX, "project_id", "url", unique=True),
        Index(PROJECT_SLUG_INDEX, "project_id", "slug", unique=True),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{ProjectRow.__tablename__}.id"))
    slug: Mapped[str] = mapped_column(Text())
    url: Mapped[str] = mapped_column(Text())
    default_branch: Mapped[str] = mapped_column(Text())
    install_command: Mapped[str] = mapped_column(Text())
    quality_gate_command: Mapped[str] = mapped_column(Text())
    unit_test_command: Mapped[str] = mapped_column(Text())
    test_globs: Mapped[list[str]] = mapped_column(JSONB())
    package_manager: Mapped[str] = mapped_column(Text())
    clone_check: Mapped[dict[str, Any]] = mapped_column(JSONB())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
