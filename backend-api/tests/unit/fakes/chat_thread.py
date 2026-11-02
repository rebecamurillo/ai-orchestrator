"""In-memory `ChatThreadRepository` and `ChatNoticeRepository` — the one fake for each port
(AD-18). Reuse them; do not write another.

They mirror what the `chat_thread` and `chat_notice` tables enforce. `add` is the adapter's
`INSERT … ON CONFLICT DO NOTHING`: a second thread at the same `(run_id, park_seq)`, the same
`ref` or the same id is not stored, and `add` answers `False`. `get_for_update` returns `get`,
since a fake has no lock to take. Both lists come back oldest first, by `(created_at, id)`.

The Project a thread belongs to is its Run's, so the thread fake reads the Run fake, and the
notice fake reads the gate records the way the anti-join does.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from datetime import datetime
from uuid import UUID

from orchestrator.domain.entities.chat_thread import ChatNotice, ChatThread, ChatThreadState
from orchestrator.domain.entities.gate_record import GateRecord
from tests.unit.fakes.runs import FakeGateRecordRepository, FakeRunRepository

ACCEPT_EVENT = "senior_accept"


class FakeChatThreadRepository:
    """Stored threads in a dictionary, keyed by id."""

    def __init__(self, runs: FakeRunRepository, threads: list[ChatThread] | None = None) -> None:
        self.runs = runs
        self.threads: dict[UUID, ChatThread] = {}
        self.calls: list[tuple[str, object]] = []
        for thread in threads or []:
            if not self.add(thread):
                raise ValueError(f"thread {thread.id} conflicts with a stored one")

    def add(self, thread: ChatThread) -> bool:
        self.calls.append(("add", thread.id))
        if thread.id in self.threads or self._conflicts(thread):
            return False
        self.threads[thread.id] = thread
        return True

    def get(self, thread_id: UUID) -> ChatThread | None:
        self.calls.append(("get", thread_id))
        return self.threads.get(thread_id)

    def get_for_update(self, thread_id: UUID) -> ChatThread | None:
        self.calls.append(("get_for_update", thread_id))
        return self.threads.get(thread_id)

    def get_by_stop(self, run_id: UUID, park_seq: int) -> ChatThread | None:
        self.calls.append(("get_by_stop", (run_id, park_seq)))
        return next(
            (t for t in self.threads.values() if (t.run_id, t.park_seq) == (run_id, park_seq)),
            None,
        )

    def list_open_for_project(self, project_id: UUID) -> list[ChatThread]:
        self.calls.append(("list_open_for_project", project_id))
        return _oldest_first(
            thread
            for thread in self.threads.values()
            if thread.state == "open" and self._project_of(thread) == project_id
        )

    def list_by_state(self, state: ChatThreadState) -> list[ChatThread]:
        self.calls.append(("list_by_state", state))
        return _oldest_first(thread for thread in self.threads.values() if thread.state == state)

    def update(self, thread: ChatThread) -> None:
        self.calls.append(("update", thread.id))
        if thread.id not in self.threads:
            raise ValueError(f"no thread with id {thread.id} is stored")
        if self._conflicts(thread):
            raise ValueError(f"thread {thread.id} would duplicate a stored stop or ref")
        self.threads[thread.id] = thread

    def _conflicts(self, thread: ChatThread) -> bool:
        for stored in self.threads.values():
            if stored.id == thread.id:
                continue
            if (stored.run_id, stored.park_seq) == (thread.run_id, thread.park_seq):
                return True
            if thread.ref is not None and stored.ref == thread.ref:
                return True
        return False

    def _project_of(self, thread: ChatThread) -> UUID | None:
        run = self.runs.runs.get(thread.run_id)
        return None if run is None else run.project_id


class FakeChatNoticeRepository:
    """Stored notice claims in a dictionary, keyed by the gate record they claim."""

    def __init__(self, runs: FakeRunRepository, records: FakeGateRecordRepository) -> None:
        self.runs = runs
        self.records = records
        self.notices: dict[UUID, ChatNotice] = {}
        self.calls: list[tuple[str, object]] = []

    def add(self, notice: ChatNotice) -> bool:
        self.calls.append(("add", notice.gate_record_id))
        if notice.gate_record_id in self.notices:
            return False
        self.notices[notice.gate_record_id] = notice
        return True

    def unposted_accepts(self, project_id: UUID, since: datetime) -> list[GateRecord]:
        self.calls.append(("unposted_accepts", (project_id, since)))
        return sorted(
            (
                record
                for record in self.records.records.values()
                if record.event == ACCEPT_EVENT
                and record.at >= since
                and record.id not in self.notices
                and self._project_of(record) == project_id
            ),
            key=lambda record: (record.at, record.id),
        )

    def set_error(self, gate_record_id: UUID, error: str) -> None:
        self.calls.append(("set_error", gate_record_id))
        notice = self.notices.get(gate_record_id)
        if notice is not None:
            self.notices[gate_record_id] = replace(notice, error=error)

    def _project_of(self, record: GateRecord) -> UUID | None:
        run = self.runs.runs.get(record.run_id)
        return None if run is None else run.project_id


def _oldest_first(threads: Iterable[ChatThread]) -> list[ChatThread]:
    return sorted(threads, key=lambda thread: (thread.created_at, thread.id))
