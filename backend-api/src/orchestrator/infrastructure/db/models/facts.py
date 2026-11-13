"""The seven fact tables (SPEC CAP-2, AGENTS.md "Data capture"): append-only, written once.

Nothing updates or deletes a row. Money is `numeric(12, 6)` (`models/run.py`'s `MONEY`). A
`usage_fact` belongs to exactly one parent, a `fact_set` or a `gateway_read`, which the
`ck_usage_fact_one_parent` check holds at the database.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.run import ATTEMPT_TABLE, MONEY, RUN_TABLE

FACT_SET_TABLE = "fact_set"
GATEWAY_READ_TABLE = "gateway_read"
USAGE_FACT_TABLE = "usage_fact"
REQUEST_FACT_TABLE = "request_fact"
ACTIVITY_FACT_TABLE = "activity_fact"
GAP_FACT_TABLE = "gap_fact"
EVENT_FACT_TABLE = "event_fact"

FACT_SET_UNIQUE = "uq_fact_set_attempt_extractor_version"
USAGE_FACT_ONE_PARENT = "one_parent"
ONE_PARENT_CONDITION = "(fact_set_id IS NULL) <> (gateway_read_id IS NULL)"


class FactSetRow(Base):
    __tablename__ = FACT_SET_TABLE
    __table_args__ = (
        UniqueConstraint("attempt_id", "extractor", "extractor_version", name=FACT_SET_UNIQUE),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{ATTEMPT_TABLE}.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    extractor: Mapped[str] = mapped_column(Text())
    extractor_version: Mapped[int] = mapped_column(Integer())
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text())
    reason: Mapped[str | None] = mapped_column(Text(), nullable=True)


class GatewayReadRow(Base):
    __tablename__ = GATEWAY_READ_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{ATTEMPT_TABLE}.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id"))
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    trigger: Mapped[str] = mapped_column(Text())
    rows: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    calls: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    provisional: Mapped[bool] = mapped_column(Boolean())
    capped: Mapped[bool] = mapped_column(Boolean(), server_default=false())
    usd: Mapped[Decimal] = mapped_column(MONEY)
    prompt: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    completion: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)


class UsageFactRow(Base):
    __tablename__ = USAGE_FACT_TABLE
    __table_args__ = (CheckConstraint(ONE_PARENT_CONDITION, name=USAGE_FACT_ONE_PARENT),)

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    fact_set_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey(f"{FACT_SET_TABLE}.id"), index=True, nullable=True
    )
    gateway_read_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey(f"{GATEWAY_READ_TABLE}.id"), index=True, nullable=True
    )
    source: Mapped[str] = mapped_column(Text())
    model: Mapped[str | None] = mapped_column(Text(), nullable=True)
    conversation: Mapped[str | None] = mapped_column(Text(), nullable=True)
    subagent_type: Mapped[str | None] = mapped_column(Text(), nullable=True)
    usage_class: Mapped[str] = mapped_column("class", Text())
    tokens: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)
    usd: Mapped[Decimal | None] = mapped_column(MONEY, nullable=True)
    calls: Mapped[int | None] = mapped_column(BigInteger(), nullable=True)


class RequestFactRow(Base):
    __tablename__ = REQUEST_FACT_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{FACT_SET_TABLE}.id"), index=True
    )
    message_id: Mapped[str] = mapped_column(Text())
    model: Mapped[str] = mapped_column(Text())
    conversation: Mapped[str] = mapped_column(Text())
    at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_uncached: Mapped[int] = mapped_column(BigInteger())
    cache_read: Mapped[int] = mapped_column(BigInteger())
    cache_write_5m: Mapped[int] = mapped_column(BigInteger())
    cache_write_1h: Mapped[int] = mapped_column(BigInteger())
    output: Mapped[int] = mapped_column(BigInteger())


class ActivityFactRow(Base):
    __tablename__ = ACTIVITY_FACT_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{FACT_SET_TABLE}.id"), index=True
    )
    conversation: Mapped[str] = mapped_column(Text())
    tool: Mapped[str] = mapped_column(Text())
    calls: Mapped[int] = mapped_column(BigInteger())
    errors: Mapped[int] = mapped_column(BigInteger())
    files_read: Mapped[int] = mapped_column(BigInteger())
    files_edited: Mapped[int] = mapped_column(BigInteger())
    test_runs: Mapped[int] = mapped_column(BigInteger())
    messages: Mapped[int] = mapped_column(BigInteger())


class GapFactRow(Base):
    __tablename__ = GAP_FACT_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{FACT_SET_TABLE}.id"), index=True
    )
    conversation: Mapped[str] = mapped_column(Text())
    messages: Mapped[int] = mapped_column(BigInteger())
    first_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gaps_s: Mapped[list[int]] = mapped_column(ARRAY(Integer()))


class EventFactRow(Base):
    __tablename__ = EVENT_FACT_TABLE

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    fact_set_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{FACT_SET_TABLE}.id"), index=True
    )
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    conversation: Mapped[str] = mapped_column(Text())
    kind: Mapped[str] = mapped_column(Text())
    path: Mapped[str | None] = mapped_column(Text(), nullable=True)
    command: Mapped[str | None] = mapped_column(Text(), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer(), nullable=True)
