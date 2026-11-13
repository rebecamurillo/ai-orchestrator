"""`run_repository` and `run_commit` (AGENTS.md "Data capture"): side records, never deleted.

Only `head_pushed` and `head_local_at_end` are ever updated.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.domain.entities.run_records import MADE_BY
from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.run import RUN_TABLE

RUN_REPOSITORY_TABLE = "run_repository"
RUN_COMMIT_TABLE = "run_commit"
RUN_REPOSITORY_UNIQUE = "uq_run_repository_run_path"
RUN_COMMIT_UNIQUE = "uq_run_commit_run_path_sha"
MADE_BY_CHECK = "made_by"


class RunRepositoryRow(Base):
    __tablename__ = RUN_REPOSITORY_TABLE
    __table_args__ = (UniqueConstraint("run_id", "path", name=RUN_REPOSITORY_UNIQUE),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    path: Mapped[str] = mapped_column(Text())
    remote_url: Mapped[str] = mapped_column(Text())
    base_branch: Mapped[str] = mapped_column(Text())
    branch: Mapped[str] = mapped_column(Text())
    base_tip: Mapped[str] = mapped_column(Text())
    head_pushed: Mapped[str | None] = mapped_column(Text(), nullable=True)
    head_local_at_end: Mapped[str | None] = mapped_column(Text(), nullable=True)


class RunCommitRow(Base):
    __tablename__ = RUN_COMMIT_TABLE
    __table_args__ = (
        UniqueConstraint("run_id", "path", "sha", name=RUN_COMMIT_UNIQUE),
        CheckConstraint(
            "made_by IN (" + ", ".join(f"'{token}'" for token in MADE_BY) + ")",
            name=MADE_BY_CHECK,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    path: Mapped[str] = mapped_column(Text())
    sha: Mapped[str] = mapped_column(Text())
    made_by: Mapped[str] = mapped_column(Text())
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
