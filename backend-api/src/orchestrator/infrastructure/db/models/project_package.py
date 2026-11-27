"""The `project_package` table (AD-39): one row per Project that installed a package."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.project import TABLE_NAME as PROJECT_TABLE

PROJECT_PACKAGE_TABLE = "project_package"
REPOSITORY_TABLE = "repository"


class ProjectPackageRow(Base):
    """One installed package."""

    __tablename__ = PROJECT_PACKAGE_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{PROJECT_TABLE}.id"), unique=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{REPOSITORY_TABLE}.id"))
    path: Mapped[str] = mapped_column(Text())
    ref: Mapped[str] = mapped_column(Text())
    sha: Mapped[str] = mapped_column(Text())
    name: Mapped[str] = mapped_column(Text())
    declaration: Mapped[dict[str, Any]] = mapped_column(JSONB())
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
