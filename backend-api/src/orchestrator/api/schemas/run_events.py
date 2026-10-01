"""The HTTP shape of `GET /runs/{run_id}/events` (agent-delivery-kit plan §7 v2).

Deliberately narrow: a watcher reads this to learn *whether* to look, and `GET /runs/{id}/
detail` to learn *what happened*. `changed` is the only field this endpoint adds to the read
model — `False` means the wait ran out with the Run as the caller already knew it.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.application.use_cases.run_events import RunEvent
from orchestrator.domain.statuses import ParkKind, RunStatus, SignalKind


class RunEventsOut(BaseModel):
    """One Run's current state, and whether it moved while this request was held open."""

    run_id: UUID
    status: RunStatus
    #: The Run row's last-write time, and the value to pass back as `?since=` on the next
    #: call. `null` only for a Run no database has written, which no route can reach.
    updated_at: UtcTimestamp | None
    #: `True` when `status` or `updated_at` left what this request started from.
    changed: bool
    #: The only list a Signal may be chosen from (SPEC CAP-9).
    admitted_signals: tuple[SignalKind, ...]
    spend_usd: MoneyStr
    budget_usd: MoneyStr | None
    park_kind: ParkKind | None
    park_path: str | None

    @classmethod
    def of(cls, event: RunEvent, *, changed: bool) -> RunEventsOut:
        return cls(
            run_id=event.run_id,
            status=event.status,
            updated_at=event.updated_at,
            changed=changed,
            admitted_signals=event.admitted_signals,
            spend_usd=event.spend_usd,
            budget_usd=event.budget_usd,
            park_kind=event.park_kind,
            park_path=event.park_path,
        )
