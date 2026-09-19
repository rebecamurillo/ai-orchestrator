"""The HTTP shape of `GET /queue` (`api/schemas/queue.py`, SPEC CAP-11).

The router test (`test_queue_router.py`) proves this renders correctly through a real
request; this module exercises `QueueItemOut.of` and `QueueOut.of` directly, the way
`test_signals_schema.py` does for `SignalIn.as_signal()`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from orchestrator.api.schemas.queue import QueueItemOut, QueueOut
from orchestrator.application.use_cases.queue import QueueRow, QueueView
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id

NOW = datetime(2026, 9, 7, tzinfo=UTC)
WAITING_SECONDS = 12.0
MAX_ACTIVE_RUNS = 3


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=0,  # type: ignore[arg-type]
        created_at=NOW,
    )


def a_row(**overrides: object) -> QueueRow:
    fields: dict[str, object] = {
        "position": None,
        "run": a_run(),
        "next_step_label": "install",
        "reason": "running",
        "waiting_since": NOW,
        "waiting_seconds": WAITING_SECONDS,
    }
    fields.update(overrides)
    return QueueRow(**fields)  # type: ignore[arg-type]


def test_queue_item_out_of_carries_every_field() -> None:
    # operator revision 2026-09-15: partition by (repository, branch)
    row = a_row(position=1, reason="branch held by epic · main")

    item = QueueItemOut.of(row)

    assert item.position == 1
    assert item.run.id == row.run.id
    assert item.next_step_label == "install"
    # operator revision 2026-09-15: partition by (repository, branch)
    assert item.reason == "branch held by epic · main"
    assert item.waiting_seconds == WAITING_SECONDS


def test_queue_out_of_carries_the_envelope_and_the_ceiling() -> None:
    view = QueueView(items=[a_row()], max_active_runs=MAX_ACTIVE_RUNS)

    body = QueueOut.of(view)

    assert len(body.items) == 1
    assert body.next_cursor is None
    assert body.max_active_runs == MAX_ACTIVE_RUNS
