"""The `template` and `template_version` tables (SPEC CAP-3, AD-15).

Two tables because two things never change at the same rate: `template` is one row per
name, holding `description` denormalised from the latest version's parsed YAML so
`GET /templates` never re-parses anything to answer a list; `template_version` is one
immutable row per `(name, version)`, and nothing here exposes an update — AD-15's rule that
a saved version never changes is enforced by this module having no method that would.

`calls` is `jsonb`: a short, ordered list of `{name, version}` pairs, always read whole with
the version and never queried into — `callers_of` scans every row instead of indexing into
this column, the same trade `Project.env_vars_enc` already makes for a column this shape.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base

TEMPLATE_TABLE = "template"
TEMPLATE_VERSION_TABLE = "template_version"

#: The unique index a version's `(name, version)` primary key relies on.
NAME_VERSION_INDEX = "ix_template_version_name_version"


class TemplateRow(Base):
    """One row per Template name: its description, denormalised, and when it first saved."""

    __tablename__ = TEMPLATE_TABLE

    name: Mapped[str] = mapped_column(Text(), primary_key=True)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TemplateVersionRow(Base):
    """One immutable stored Template Version. No column here is ever updated (AD-15)."""

    __tablename__ = TEMPLATE_VERSION_TABLE
    __table_args__ = (Index(NAME_VERSION_INDEX, "name", "version", unique=True),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    name: Mapped[str] = mapped_column(Text(), ForeignKey(f"{TemplateRow.__tablename__}.name"))
    version: Mapped[int] = mapped_column(Integer())
    yaml: Mapped[str] = mapped_column(Text())
    hash: Mapped[str] = mapped_column(Text())
    calls: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
