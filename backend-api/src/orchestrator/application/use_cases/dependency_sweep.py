"""Startup sweep for dependency-waiting Runs whose predecessor terminated before boot.

When the process crashes between a predecessor reaching a terminal status (`done`,
`failed`, or `cancelled`) and the dependent being enqueued or parked, the dependent
is left in `queued` with `engine_ref={}` and `after_run_id` still set. This sweep
re-applies the resolution on startup, making crash recovery idempotent (AD-12).

This is a pure application function: it reads from the repositories through `WriterPorts`
and calls the same `_enqueue_dependents` / `_park_dependents` helpers the two main writers
(`apply_step_result`, `signal_run`) use at run time.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.use_cases.writers import (
    WriterPorts,
    _enqueue_dependents,
    _park_dependents,
)
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.statuses import TERMINAL_RUN


def sweep_dependency_waiting(ports: WriterPorts, engine: WorkflowEngine | None) -> None:
    """Re-resolve any dependency-waiting Run left un-enqueued or un-parked by a crash.

    Finds every `queued` Run whose `after_run_id` is set and `engine_ref` is empty, then
    groups them by predecessor and checks each predecessor's status once:

    - predecessor `done`: two-phase enqueue, identical to the successful run-time path.
    - predecessor `failed | cancelled`: park in the same UoW, identical to the failed path.
    - predecessor not found or not yet terminal: skip — nothing to do yet.

    Idempotent: `list_by_after_run_id` returns only `engine_ref == {}` rows, so a run that
    was already enqueued in a prior sweep is invisible here. Grouping by predecessor ensures
    each predecessor's resolution is applied exactly once even when multiple dependents wait
    for it (preventing double gate records from repeated `_park_dependents` calls).
    """
    queued_runs = ports.runs.list_by_status("queued")
    waiting = [r for r in queued_runs if r.after_run_id is not None and not r.engine_ref]
    if not waiting:
        return

    # Group by predecessor ID to call the resolution helpers once per predecessor.
    predecessor_ids: set[UUID] = {r.after_run_id for r in waiting}  # type: ignore[misc]
    for pred_id in predecessor_ids:
        predecessor = ports.runs.get(pred_id)
        if predecessor is None or predecessor.status not in TERMINAL_RUN:
            continue
        if predecessor.status == "done":
            _enqueue_dependents(ports, engine, predecessor)
        else:
            # failed or cancelled
            with ports.uow:
                _park_dependents(ports, predecessor)
                ports.uow.commit()
