"""`start_attempt` (SPEC CAP-5): one row leaves the queue, and an Attempt exists (AD-8).

This is the smaller of the two execution writers, and it is deliberately its own unit of
work: the walker commits it *before* the executor runs, so a backend that dies mid-step is
found afterwards with the row `running` and an Attempt whose start half is stored, which is
what lets FR-12 report an interrupted attempt instead of losing it.

Three things happen, in this order, and nothing else:

1. **The Run starts, once.** A Run in `queued` becomes `running` with `started_at` and one
   `start` gate record. A Run already `running` is left alone — the second row of a plan is
   not a second beginning. Any other status is a walker bug and `run_transition` says so:
   `start_attempt` on a parked or cancelled Run raises `InvalidTransition` (a 500), because
   only `signal_run` resumes a Run and only the walker calls this.
2. **The row starts.** `queued → running`, through `step_transition`.
3. **The Attempt is added**, numbered from the row's own latest: `n + 1`, or `1` for a row
   that has never run. `AttemptRepository.add` refuses a duplicate `(step_run_id, n)`, so a
   second start on the same row while one is stored is a stored refusal, not a silent
   overwrite.

`engine_ref` is opaque JSON the engine adapter owns (AD-6): it is passed through to the
Attempt and never read here.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from orchestrator.application.use_cases.writers import (
    RUN_STARTED,
    Entry,
    WriterPorts,
    record,
    require_row,
    require_run,
    set_row,
    set_run,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import run_transition, step_transition

#: The status a Run is already in when a row that is not its first starts.
RUNNING = "running"


def start_attempt(
    ports: WriterPorts,
    run_id: UUID,
    seq: int,
    *,
    engine_ref: dict[str, Any] | None = None,
) -> Attempt:
    """Move one row `queued → running` and store the Attempt that is running it."""
    with ports.uow:
        run = require_run(ports, run_id)
        row = require_row(ports, run_id, seq)
        _start_run(ports, run)
        set_row(ports, row, status=step_transition(row.status, "start"))
        previous = ports.attempts.get_latest(row.id)
        attempt = Attempt(
            id=new_id(),
            run_id=run.id,
            step_run_id=row.id,
            n=previous.n + 1 if previous is not None else 1,
            status="running",
            started_at=ports.clock.now(),
            engine_ref=dict(engine_ref or {}),
        )
        ports.attempts.add(attempt)
        ports.uow.commit()
    return attempt


def _start_run(ports: WriterPorts, run: Run) -> None:
    """The Run's own beginning, written once: `queued → running` plus the `start` record."""
    if run.status == RUNNING:
        return
    started = set_run(
        ports,
        run,
        status=run_transition(run.status, "start"),
        started_at=ports.clock.now(),
    )
    record(ports, started, Entry(event="start", actor="machine", text=RUN_STARTED))
