"""The `chat_thread` and `chat_notice` tables (AD-25, story 3-3).

`chat_thread` is unique on `(run_id, park_seq)` and on `ref`, and those two keys are what
make `chat_poll`'s claim safe when two fires overlap. Only `ref` (null while `posting`),
`cursor`, `error`, `last_reminded_at` and 4-2's six close columns are nullable. Four named
CHECKs hold the two notice alphabets and their order: a closing notice only on a `closed`
thread, a mention notice only after a posted closing notice. `chat_notice` is a claim row keyed by
the `senior_accept` gate record it posts. Both go with their Run (`ON DELETE CASCADE`); no
column defaults to the database's `now()`, since every thread time is the `Clock`'s.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from orchestrator.infrastructure.db.base import Base
from orchestrator.infrastructure.db.models.project_channel import PROVIDER_CHECK
from orchestrator.infrastructure.db.models.run import GATE_RECORD_TABLE, RUN_TABLE

CHAT_THREAD_TABLE = "chat_thread"
CHAT_NOTICE_TABLE = "chat_notice"
STATE_CHECK = "state IN ('posting', 'open', 'closed', 'failed')"
#: Story 4-2's four CHECKs, by name; migration 0030 writes the same text.
CLOSE_CHECKS = {
    "close_notice": "close_notice IN ('due', 'sending', 'posted', 'failed')",
    "mention_notice": "mention_notice IN ('sending', 'posted', 'failed')",
    "close_notice_closed": "close_notice IS NULL OR state = 'closed'",
    "mention_notice_after_close": "mention_notice IS NULL OR close_notice = 'posted'",
}


class ChatThreadRow(Base):
    """One stop's thread."""

    __tablename__ = CHAT_THREAD_TABLE
    __table_args__ = (
        UniqueConstraint("run_id", "park_seq"),
        UniqueConstraint("ref"),
        CheckConstraint(STATE_CHECK, name="state"),
        CheckConstraint(PROVIDER_CHECK, name="provider"),
        *(CheckConstraint(text, name=name) for name, text in CLOSE_CHECKS.items()),
    )

    id: Mapped[UUID] = mapped_column(Uuid(), primary_key=True)
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id", ondelete="CASCADE"))
    park_seq: Mapped[int] = mapped_column(Integer())
    park_kind: Mapped[str] = mapped_column(Text())
    provider: Mapped[str] = mapped_column(Text())
    channel_id: Mapped[str] = mapped_column(Text())
    ref: Mapped[str | None] = mapped_column(Text(), nullable=True)
    cursor: Mapped[str | None] = mapped_column(Text(), nullable=True)
    state: Mapped[str] = mapped_column(Text())
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    last_reminded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    close_notice: Mapped[str | None] = mapped_column(Text(), nullable=True)
    close_notice_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mention_notice: Mapped[str | None] = mapped_column(Text(), nullable=True)
    mention_notice_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    mention_cursor: Mapped[str | None] = mapped_column(Text(), nullable=True)


class ChatNoticeRow(Base):
    """The claim on posting one `senior_accept` record."""

    __tablename__ = CHAT_NOTICE_TABLE

    gate_record_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey(f"{GATE_RECORD_TABLE}.id", ondelete="CASCADE"), primary_key=True
    )
    run_id: Mapped[UUID] = mapped_column(Uuid(), ForeignKey(f"{RUN_TABLE}.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
