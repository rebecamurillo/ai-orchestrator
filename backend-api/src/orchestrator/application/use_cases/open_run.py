"""`open_run` (story 8-3): record `last_opened_before` and update `last_opened_at` when a
Run's detail is first fetched per navigation (`?opened=true`).

**Not a status writer.** `last_opened_before` and `last_opened_at` are the only new Run
fields written outside the two status writers (AD-8 exception: explicit use case, side-effect
of the existing detail endpoint). The pattern mirrors `ActivityPorts` in `activity.py`: a
small, distinct dependency set — `runs`, `uow`, and a `Clock` — with no `records`, `gateway`,
`steps`, or `attempts`.

**Swap semantics.** On each `open_run` call:
1. `last_opened_before` ← current `run.last_opened_at` (may be `None` on first open)
2. `last_opened_at` ← `clock.now()`

The caller (`detail` router) calls this before `build_detail` so the response reflects the
just-updated `last_opened_at`, and so `GET /runs/{id}/files` (called separately) sees the
freshly committed `last_opened_before` for the changed-marks computation.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class OpenRunPorts:
    """What `open_run` reads and writes through.

    Mirrors the `ActivityPorts` shape: a smaller dependency set than `WriterPorts`, with
    only the ports this one use case needs.
    """

    runs: RunRepository
    uow: UnitOfWork
    clock: Clock


def open_run(ports: OpenRunPorts, run_id: UUID) -> None:
    """Swap `last_opened_before ← last_opened_at`, set `last_opened_at = clock.now()`.

    `None` from the repository → `NotFound`, which `api/errors.py` maps to 404.
    No-op on the fields other than the two `last_opened_*` timestamps.

    The UoW is entered by `open_run_ports` before yielding (same as every other provider);
    this function calls `commit()` directly rather than re-entering the context manager.
    """
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run with id {run_id}")
    updated = run.model_copy(
        update={
            "last_opened_before": run.last_opened_at,
            "last_opened_at": ports.clock.now(),
        }
    )
    ports.runs.update(updated)
    ports.uow.commit()
