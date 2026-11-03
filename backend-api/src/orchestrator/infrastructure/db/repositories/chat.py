"""The SQLAlchemy adapters for `ChatThreadRepository` and `ChatNoticeRepository` (AD-25).

They mirror `tests/unit/fakes/chat_thread.py`. Each `add` is one `INSERT … ON CONFLICT DO
NOTHING` with no conflict target, so a taken stop, `ref` or id, or an already claimed
record, writes nothing and answers `False` (`rowcount` is 1 only for a row written): that is
what keeps two overlapping fires from both posting. `get_for_update` takes a row lock and
re-reads the row, as `runs.py::get_for_update` does.

4-2's three notice lists hold every filter in the query: `list_notices_due` and
`list_watched` join the Run for its Project, and `list_watched` is cut at its `limit` there.

`unposted_accepts` is an anti-join: every `senior_accept` on the Project's Runs at or after
`since` with no `chat_notice` row, with no filter on the Run's status.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from sqlalchemy import exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from orchestrator.domain.entities.chat_thread import (
    ChatNotice,
    ChatThread,
    ChatThreadState,
    NoticeState,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ports.chat import ChatProvider
from orchestrator.domain.statuses import ParkKind
from orchestrator.infrastructure.db.models.chat import ChatNoticeRow, ChatThreadRow
from orchestrator.infrastructure.db.models.run import GateRecordRow, RunRow
from orchestrator.infrastructure.db.repositories.gate_records import to_entity as to_record

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

ACCEPT_EVENT = "senior_accept"


def thread_values(thread: ChatThread) -> dict[str, Any]:
    """Every column of the `chat_thread` table, keyed by name."""
    return {
        "id": thread.id,
        "run_id": thread.run_id,
        "park_seq": thread.park_seq,
        "park_kind": thread.park_kind,
        "provider": thread.provider,
        "channel_id": thread.channel_id,
        "ref": thread.ref,
        "cursor": thread.cursor,
        "state": thread.state,
        "error": thread.error,
        "last_reminded_at": thread.last_reminded_at,
        "created_at": thread.created_at,
        "updated_at": thread.updated_at,
        "closed_at": thread.closed_at,
        "close_notice": thread.close_notice,
        "close_notice_at": thread.close_notice_at,
        "mention_notice": thread.mention_notice,
        "mention_notice_at": thread.mention_notice_at,
        "mention_cursor": thread.mention_cursor,
    }


def to_thread(row: ChatThreadRow) -> ChatThread:
    return ChatThread(
        id=row.id,
        run_id=row.run_id,
        park_seq=row.park_seq,
        park_kind=cast(ParkKind, row.park_kind),
        provider=cast(ChatProvider, row.provider),
        channel_id=row.channel_id,
        ref=row.ref,
        cursor=row.cursor,
        state=cast(ChatThreadState, row.state),
        error=row.error,
        last_reminded_at=row.last_reminded_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
        closed_at=row.closed_at,
        close_notice=cast("NoticeState | None", row.close_notice),
        close_notice_at=row.close_notice_at,
        mention_notice=cast("NoticeState | None", row.mention_notice),
        mention_notice_at=row.mention_notice_at,
        mention_cursor=row.mention_cursor,
    )


class SQLAlchemyChatThreadRepository:
    """Stored stop threads, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, thread: ChatThread) -> bool:
        statement = (
            insert(ChatThreadRow.__table__).values(**thread_values(thread)).on_conflict_do_nothing()
        )
        result = self._session.execute(statement)
        return bool(result.rowcount == 1)

    def get(self, thread_id: UUID) -> ChatThread | None:
        row = self._session.get(ChatThreadRow, thread_id)
        return None if row is None else to_thread(row)

    def get_for_update(self, thread_id: UUID) -> ChatThread | None:
        statement = (
            select(ChatThreadRow)
            .where(ChatThreadRow.id == thread_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        row = self._session.scalars(statement).first()
        return None if row is None else to_thread(row)

    def get_by_stop(self, run_id: UUID, park_seq: int) -> ChatThread | None:
        statement = select(ChatThreadRow).where(
            ChatThreadRow.run_id == run_id, ChatThreadRow.park_seq == park_seq
        )
        row = self._session.scalars(statement).first()
        return None if row is None else to_thread(row)

    def list_open_for_project(self, project_id: UUID) -> list[ChatThread]:
        statement = (
            select(ChatThreadRow)
            .join(RunRow, RunRow.id == ChatThreadRow.run_id)
            .where(RunRow.project_id == project_id, ChatThreadRow.state == "open")
            .order_by(ChatThreadRow.created_at, ChatThreadRow.id)
        )
        return [to_thread(row) for row in self._session.scalars(statement).all()]

    def list_by_state(self, state: ChatThreadState) -> list[ChatThread]:
        statement = (
            select(ChatThreadRow)
            .where(ChatThreadRow.state == state)
            .order_by(ChatThreadRow.created_at, ChatThreadRow.id)
        )
        return [to_thread(row) for row in self._session.scalars(statement).all()]

    def list_notices_due(self, project_id: UUID) -> list[ChatThread]:
        statement = (
            select(ChatThreadRow)
            .join(RunRow, RunRow.id == ChatThreadRow.run_id)
            .where(RunRow.project_id == project_id, ChatThreadRow.close_notice == "due")
            .order_by(ChatThreadRow.closed_at, ChatThreadRow.id)
        )
        return [to_thread(row) for row in self._session.scalars(statement).all()]

    def list_notices_in(self, state: NoticeState) -> list[ChatThread]:
        statement = (
            select(ChatThreadRow)
            .where(or_(ChatThreadRow.close_notice == state, ChatThreadRow.mention_notice == state))
            .order_by(ChatThreadRow.created_at, ChatThreadRow.id)
        )
        return [to_thread(row) for row in self._session.scalars(statement).all()]

    def list_watched(
        self,
        project_id: UUID,
        provider: ChatProvider,
        channel_id: str,
        closed_since: datetime,
        limit: int,
    ) -> list[ChatThread]:
        statement = (
            select(ChatThreadRow)
            .join(RunRow, RunRow.id == ChatThreadRow.run_id)
            .where(
                RunRow.project_id == project_id,
                ChatThreadRow.state == "closed",
                ChatThreadRow.close_notice == "posted",
                ChatThreadRow.mention_notice.is_(None),
                ChatThreadRow.provider == provider,
                ChatThreadRow.channel_id == channel_id,
                ChatThreadRow.closed_at >= closed_since,
            )
            .order_by(ChatThreadRow.closed_at.desc(), ChatThreadRow.id.desc())
            .limit(limit)
        )
        return [to_thread(row) for row in self._session.scalars(statement).all()]

    def update(self, thread: ChatThread) -> None:
        values = thread_values(thread)
        values.pop("id")
        self._session.execute(
            update(ChatThreadRow).where(ChatThreadRow.id == thread.id).values(**values)
        )


class SQLAlchemyChatNoticeRepository:
    """Claims on posting `senior_accept` records, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, notice: ChatNotice) -> bool:
        statement = (
            insert(ChatNoticeRow.__table__)
            .values(
                gate_record_id=notice.gate_record_id,
                run_id=notice.run_id,
                created_at=notice.created_at,
                error=notice.error,
            )
            .on_conflict_do_nothing()
        )
        result = self._session.execute(statement)
        return bool(result.rowcount == 1)

    def unposted_accepts(self, project_id: UUID, since: datetime) -> list[GateRecord]:
        claimed = exists().where(ChatNoticeRow.gate_record_id == GateRecordRow.id)
        statement = (
            select(GateRecordRow)
            .join(RunRow, RunRow.id == GateRecordRow.run_id)
            .where(
                RunRow.project_id == project_id,
                GateRecordRow.event == ACCEPT_EVENT,
                GateRecordRow.at >= since,
                ~claimed,
            )
            .order_by(GateRecordRow.at, GateRecordRow.id)
        )
        return [to_record(row) for row in self._session.scalars(statement).all()]

    def set_error(self, gate_record_id: UUID, error: str) -> None:
        self._session.execute(
            update(ChatNoticeRow)
            .where(ChatNoticeRow.gate_record_id == gate_record_id)
            .values(error=error)
        )
