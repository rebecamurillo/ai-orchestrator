"""The `Notifier` port: telling someone outside the system that a Run needs them or ended.

Best-effort by contract. `notify` returns nothing and raises nothing the caller must handle:
a notification that cannot be delivered is the adapter's to log, never a reason for a step or
a status transition to fail.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.statuses import ParkKind, RunStatus

#: The statuses a Run is announced on entering. `running` and `queued` are not news.
NOTIFIED_STATUSES: frozenset[RunStatus] = frozenset({"needs_you", "done", "failed", "cancelled"})


@dataclass(frozen=True)
class RunNotification:
    """One Run transition worth telling someone about.

    `reason` is the park's own sentence for `needs_you`, and the stopping sentence for a
    terminal status when the transition has one (the record carries it, the Run row does not).
    """

    run_id: UUID
    project: str
    repository: str
    template: str
    status: RunStatus
    park_kind: ParkKind | None
    reason: str | None
    step_path: str | None
    attempt_id: UUID | None
    spend_usd: Decimal
    occurred_at: datetime


@runtime_checkable
class Notifier(Protocol):
    """Delivers one `RunNotification`; never raises."""

    def notify(self, event: RunNotification) -> None:
        """Hand the event to the outside world, or drop it after logging why."""
        ...
