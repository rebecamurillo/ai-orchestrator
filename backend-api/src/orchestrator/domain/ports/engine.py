"""The `WorkflowEngine` port (AD-6): the durable engine, reached only through this shape.

`create_run` (4.4) is the first caller — `enqueue`, and nothing else here — but the whole
protocol is written now, transcribed from the spine, so a later story never has to widen an
interface a use case already depends on. DBOS is not named anywhere in this module: it
appears only in `infrastructure/dbos/` (4.6), and `application/` reaches it through this
port and nothing else.

`engine_ref` is opaque JSON (AD-6): `enqueue` returns it and `Run.engine_ref` stores it
whole, and nothing outside the real adapter ever reads a key of it. `attempt_record` is the
walker's own way back in after a restart — 4.4 never calls it — so its shape is a plain,
JSON-shaped envelope rather than anything the durable engine's own record format dictates.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.values import Signal

#: Whether a queued Run is running behind the engine's own concurrency limit (`enqueued`)
#: or waiting on this port's own queue, ahead of that (`pending`) — `list_queue` (4.11)
#: reports both; `create_run` (4.4) never reads this itself.
QueueState = Literal["enqueued", "pending"]


@dataclass(frozen=True)
class QueueEntry:
    """One row of `GET /queue` (SPEC CAP-11): a queued Run, its state and its position."""

    run_id: UUID
    engine_state: QueueState
    #: `None` once the engine itself is running the Run — a position is a queue's own idea.
    position: int | None
    enqueued_at: datetime


@dataclass(frozen=True)
class EngineRecord:
    """What the walker (4.6) reads back for one attempt after a restart.

    Opaque beyond `outcome`: the durable engine's own record carries whatever it needs to
    resume, and this module does not know that shape in advance (AD-6) — `payload` is where
    it lives until 4.6 defines what it reads out of it.
    """

    outcome: str
    payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class WorkflowEngine(Protocol):
    """The durable engine, behind one interface (AD-6). `application/` never imports DBOS."""

    def enqueue(self, run_id: UUID, partition_key: UUID) -> dict[str, Any]:
        """Put a Run behind its Repository's partition (AD-12); return its `engine_ref`."""
        ...

    def signal(self, run_id: UUID, signal: Signal) -> None:
        """Deliver one Operator signal (AD-13) to a Run's single `recv` wait."""
        ...

    def cancel(self, run_id: UUID) -> None:
        """Stop a Run's workflow — the engine's own half of a `cancel` signal."""
        ...

    def list_queue(self) -> list[QueueEntry]:
        """Every Run this engine is holding, queued or pending, oldest first."""
        ...

    def attempt_record(self, engine_ref: dict[str, Any]) -> EngineRecord | None:
        """What the engine itself knows about one attempt, or `None` if it knows nothing."""
        ...

    def schedule(self, name: str, cron: str, job: Callable[[], None]) -> None:
        """Register a recurring job (SPEC CAP-11: `clone_check` daily, `worktree_gc` at 7d)."""
        ...
