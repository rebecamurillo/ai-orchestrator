"""A process-local `WorkflowEngine` (AD-6) — every method of the port, none of it durable.

4.4's own scope is the interface and `create_run`'s one call to `enqueue`; the durable
engine behind `WorkflowEngine` — DBOS, surviving a restart, serialising two Runs on one
Repository — is 4.6's walker, not this story's. `POST /runs` still has to answer for real
against the running stack (the schemathesis gate fuzzes every published operation and
refuses any 5xx), so this class is what `main.py` wires until 4.6 replaces it: an
`engine_ref` that is nothing but a counter, a queue that lives only as long as the process,
and `attempt_record`/`schedule` as no-ops, because nothing yet reads or calls either. A
restart loses every entry here — 4.4 does not claim otherwise; `Run.status` still says
`queued`, and nothing in this story or the next one reads this queue to decide what runs.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from orchestrator.domain.ports.engine import EngineRecord, QueueEntry
from orchestrator.domain.values import Signal


class LocalWorkflowEngine:
    """Satisfies `WorkflowEngine` in one process, with no durability across a restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queue: dict[UUID, QueueEntry] = {}
        self._next_ref = 0

    def enqueue(self, run_id: UUID, partition_key: UUID) -> dict[str, Any]:
        with self._lock:
            self._next_ref += 1
            ref = self._next_ref
            self._queue[run_id] = QueueEntry(
                run_id=run_id,
                engine_state="enqueued",
                position=len(self._queue) + 1,
                enqueued_at=datetime.now(UTC),
            )
        return {"engine": "local", "ref": ref}

    def signal(self, run_id: UUID, signal: Signal) -> None:
        """No walker reads a signal yet (4.5/4.6); nothing to deliver it to."""

    def cancel(self, run_id: UUID) -> None:
        with self._lock:
            self._queue.pop(run_id, None)

    def list_queue(self) -> list[QueueEntry]:
        with self._lock:
            return sorted(self._queue.values(), key=lambda entry: entry.enqueued_at)

    def attempt_record(self, engine_ref: dict[str, Any]) -> EngineRecord | None:
        """Nothing here ever ran an attempt, so there is never a record to answer with."""
        return None

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        """No scheduler runs in this process yet (CAP-11 is 4.11's)."""
