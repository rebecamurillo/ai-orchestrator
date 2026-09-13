"""`record_activity` (SM-2): increment a Run's `active_seconds` from a batched focus report.

**Not `WriterPorts`.** `ActivityPorts` is its own bundle — a different write, a different,
smaller dependency set: just `runs` and `uow`. No `records`/`clock`/`gateway`/`steps`/
`attempts`, since nothing here appends a gate record, reads the time, or touches spend.
The `SpendPorts` pattern in `spend.py` is the precedent.

`active_seconds` increments only here and is never decremented. The endpoint is allowed for
any Run status — a terminal Run still counts Operator time spent reading it.

The UoW is entered by `activity_ports` before yielding (same as every other provider in
`api/providers.py`, which must enter to have a session to build the repository around);
this function calls `commit()` directly rather than re-entering the context manager, the
same shape `open_run` uses. `spend.py` reads the other way round because its ports come
from `open_spend_ports`, which hands over a `SessionUnitOfWork` it has not entered.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork


@dataclass(frozen=True)
class ActivityPorts:
    """What `record_activity` reads and writes through. See the module docstring for
    why this is not `WriterPorts`."""

    runs: RunRepository
    uow: UnitOfWork


def record_activity(ports: ActivityPorts, run_id: UUID, focused_seconds: int) -> int:
    """Increment `run.active_seconds` by `focused_seconds` and return the new total.

    `focused_seconds` must be in `[1, 3600]` — enforced at the API boundary by Pydantic.
    `None` from the repository → `NotFound`, which `api/errors.py` maps to 404.
    """
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run with id {run_id}")
    updated = run.model_copy(update={"active_seconds": run.active_seconds + focused_seconds})
    ports.runs.update(updated)
    ports.uow.commit()
    return updated.active_seconds
