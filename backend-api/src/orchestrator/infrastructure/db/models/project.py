"""The `project` table.

Two columns carry an invariant the database is asked to hold rather than the application:
`name` and `slug` are each uniquely indexed. The use case checks both before writing, and
that check is what produces the 409 the Operator can read — but two concurrent creates
would both pass it, and the index is what stops the second from landing.

What the index does *not* do is produce a good answer. Nothing here maps psycopg's
`IntegrityError` onto `Conflict`, so a create that loses that race leaves as an unhandled
exception and a 500, not as a 409. That is the honest state of it: one Operator at a
keyboard cannot reach the race, and translating it belongs with the story that makes this
API concurrent.

`context_paths` and `env_vars_enc` are `jsonb`, not child tables. Both are short, ordered,
always read whole with the Project and never queried into; a table apiece would buy a join
and cost the order the Operator typed them in.

`env_vars_enc` holds `[{name, value_enc}]` — the name in clear so a Run can build an
environment without decrypting anything, the value as a Fernet token (AD-5). No plaintext
value is ever written to this table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base

TABLE_NAME = "project"


class ProjectRow(Base):
    """One stored Project."""

    __tablename__ = TABLE_NAME

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    # unique *indexes*: the lookup by slug and the uniqueness of both are one object each
    slug: Mapped[str] = mapped_column(Text(), unique=True, index=True)
    name: Mapped[str] = mapped_column(Text(), unique=True, index=True)
    context_text: Mapped[str] = mapped_column(Text())
    context_paths: Mapped[list[str]] = mapped_column(JSONB())
    env_vars_enc: Mapped[list[dict[str, Any]]] = mapped_column(JSONB())
    log_prompt_content: Mapped[bool] = mapped_column(Boolean())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
