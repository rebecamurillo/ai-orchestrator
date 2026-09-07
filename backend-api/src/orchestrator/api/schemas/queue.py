"""The HTTP shape of `GET /queue` (SPEC CAP-11, FR-13, FR-25).

`QueueItemOut.run` is `RunSummaryOut`, the same minimal read model `GET /runs` lists — the
brief names it `RunSummary`, and this is that type's one existing shape (`api/schemas/
runs.py`'s own docstring: "the full one is 4.12's"). `QueueOut` extends the one list
envelope (`api/schemas/common.py::Page`) with `max_active_runs`, because the brief's own
section head text reads it beside the rows, not through a second request.
"""

from __future__ import annotations

from pydantic import BaseModel

from orchestrator.api.schemas.common import Page, UtcTimestamp
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.application.use_cases.queue import QueueRow, QueueView


class QueueItemOut(BaseModel):
    """One row: a Run the engine is holding, and why it waits."""

    position: int | None
    run: RunSummaryOut
    next_step_label: str
    reason: str
    waiting_since: UtcTimestamp
    waiting_seconds: float

    @classmethod
    def of(cls, row: QueueRow) -> QueueItemOut:
        return cls(
            position=row.position,
            run=RunSummaryOut.of(row.run),
            next_step_label=row.next_step_label,
            reason=row.reason,
            waiting_since=row.waiting_since,
            waiting_seconds=row.waiting_seconds,
        )


class QueueOut(Page[QueueItemOut]):
    """`GET /queue`'s body: the rows, and the ceiling the section head names beside them."""

    max_active_runs: int

    @classmethod
    def of(cls, view: QueueView) -> QueueOut:
        return cls(
            items=[QueueItemOut.of(row) for row in view.items],
            next_cursor=None,
            max_active_runs=view.max_active_runs,
        )
