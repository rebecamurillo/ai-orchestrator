"""The `harness` table (SPEC CAP-3, AD-10): one row per name, no foreign key.

Seeded at start-up (`main.run_migrations`) with the three names the image installs;
nothing else about the table is relational, which is why `name` is the primary key rather
than a surrogate id. `last_readiness_run_id` and `lines` (SPEC CAP-8) are written only by
`application/use_cases/harness_readiness.py::evaluate`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base

HARNESS_TABLE = "harness"


class HarnessRow(Base):
    """One harness, keyed by its name."""

    __tablename__ = HARNESS_TABLE

    name: Mapped[str] = mapped_column(Text(), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean())
    last_readiness_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failing_check: Mapped[str | None] = mapped_column(Text())
    version_pin: Mapped[str] = mapped_column(Text())
    last_readiness_run_id: Mapped[UUID | None] = mapped_column(Uuid())
    #: `[{check, ok, text}]`, the last evaluation's lines in order — short, always read
    #: whole with the harness, never queried into, the same reasoning `project.jsonb`
    #: columns already carry (`infrastructure/db/models/project.py`'s own docstring).
    lines: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
