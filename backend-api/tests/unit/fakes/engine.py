"""In-memory `WorkflowEngine` — the one fake for that port (AD-18). Reuse it; do not write
another.

`committed_when_called` exists for AD-8's other half: a use case commits its unit of work
*before* it talks to the engine, so a woken workflow never reads a Run whose writes are not
durable yet. Pass the same `FakeUnitOfWork` the use case was given and each call records
whether it had committed at the moment it was made — an ordering two independent `calls`
lists cannot show.

`create_run` (4.4) only ever calls `enqueue`; the rest of the protocol is implemented
because the port declares it, and a fake that skipped a method would not satisfy
`isinstance(fake, WorkflowEngine)` (`runtime_checkable`). `enqueue` hands back an
`engine_ref` that is nothing but a counter, because AD-6 says nothing outside the real
adapter may read a key of it — a fake that put anything meaningful there would invite a
caller to.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from orchestrator.domain.ports.engine import EngineRecord, QueueEntry
from orchestrator.domain.values import Signal
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork


class FakeWorkflowEngine:
    """Records every call; queues entries in a dictionary, oldest first by insertion."""

    def __init__(
        self, *, clock: FakeClock | None = None, uow: FakeUnitOfWork | None = None
    ) -> None:
        self.calls: list[tuple[str, object]] = []
        #: `uow.committed` as each call was made — empty while no `uow` was passed.
        self.committed_when_called: list[bool] = []
        self.queue: dict[UUID, QueueEntry] = {}
        self._clock = clock or FakeClock(EPOCH)
        self._uow = uow
        self._next_ref = 0

    def _note_commit_state(self) -> None:
        if self._uow is not None:
            self.committed_when_called.append(self._uow.committed)

    def enqueue(self, run_id: UUID, partition_key: UUID) -> dict[str, Any]:
        self.calls.append(("enqueue", (run_id, partition_key)))
        self._note_commit_state()
        self._next_ref += 1
        self.queue[run_id] = QueueEntry(
            run_id=run_id,
            engine_state="enqueued",
            position=len(self.queue) + 1,
            enqueued_at=self._clock.now(),
        )
        return {"ref": self._next_ref}

    def signal(self, run_id: UUID, signal: Signal) -> None:
        self.calls.append(("signal", (run_id, signal)))
        self._note_commit_state()

    def cancel(self, run_id: UUID) -> None:
        self.calls.append(("cancel", run_id))
        self._note_commit_state()
        self.queue.pop(run_id, None)

    def list_queue(self) -> list[QueueEntry]:
        self.calls.append(("list_queue", None))
        return sorted(self.queue.values(), key=lambda entry: entry.enqueued_at)

    def attempt_record(self, engine_ref: dict[str, Any]) -> EngineRecord | None:
        self.calls.append(("attempt_record", tuple(sorted(engine_ref.items()))))
        return None

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        self.calls.append(("schedule", (name, cron)))
