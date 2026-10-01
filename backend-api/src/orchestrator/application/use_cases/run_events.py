"""One Run as a watcher sees it: the fields that say *something happened* and nothing else.

The read model behind `GET /runs/{id}/events` (agent-delivery-kit plan §7 v2). It is the
same lookup `GET /runs/{id}` makes — `get_run`, then `run_rows`, then `park_row_in` — so
`admitted_signals` is the one list an answering agent may choose a Signal from, identical to
what the Run read model offers. What it leaves out is deliberate: a park's `reason`, its
attempt log and its diff are a second call (`GET /runs/{id}/detail`), because a held
connection exists to say *when* to look, not to carry the payload.

Pure, and that is what lets the waiting live elsewhere: nothing here sleeps, reads a clock
or decides whether anything changed — `infrastructure/longpoll.py` holds the connection and
`api/routers/run_events.py` says what a change is.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.rules.signals import run_admitted_signals
from orchestrator.application.use_cases.create_run import (
    RunReadPorts,
    get_run,
    park_row_in,
    run_rows,
)
from orchestrator.domain.statuses import ParkKind, RunStatus, SignalKind


@dataclass(frozen=True)
class RunEvent:
    """What one read of a Run tells a watcher.

    `updated_at` is the Run row's own last-write timestamp, maintained by the database
    (`infrastructure/db/models/run.py`). It is `None` for a Run that has never been stored,
    which only a planner and the in-memory fakes hold.
    """

    run_id: UUID
    status: RunStatus
    updated_at: datetime | None
    admitted_signals: tuple[SignalKind, ...]
    spend_usd: Decimal
    budget_usd: Decimal | None
    park_kind: ParkKind | None
    park_path: str | None


def run_event(ports: RunReadPorts, run_id: UUID) -> RunEvent:
    """One stored Run as a watcher sees it, or `NotFound` (404)."""
    run = get_run(ports, run_id)
    rows = run_rows(ports, run)
    park_row = park_row_in(run, rows)
    return RunEvent(
        run_id=run.id,
        status=run.status,
        updated_at=run.updated_at,
        admitted_signals=run_admitted_signals(
            run,
            park_row.kind if park_row is not None else None,
            park_row_status=park_row.status if park_row is not None else None,
            rows=rows,
        ),
        spend_usd=run.spend_usd,
        budget_usd=run.budget_usd,
        park_kind=run.park_kind,
        park_path=run.park_path,
    )
