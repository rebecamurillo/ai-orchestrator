"""`list_queue` appends saved runs with `reason="saved — not started"` (story 5-3).

AC coverage:
- A saved run (status=queued, engine_ref={}) appears in list_queue with reason=REASON_SAVED,
  position=None
- A saved run sorts after all engine-queue rows (order key (3, 0))
- _order_key returns (3, 0) for reason == REASON_SAVED
- A normally queued run (engine_ref non-empty) is NOT in the saved set
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from orchestrator.application.use_cases.queue import (
    REASON_RUNNING,
    REASON_SAVED,
    QueuePorts,
    QueueRow,
    _order_key,
    list_queue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")


def a_run(*, engine_ref: dict | None = None, status: str = "queued") -> Run:
    return Run(
        id=new_id(),
        project_id=new_id(),
        repository_id=new_id(),
        template_name="epic",
        template_version=1,
        status=status,  # type: ignore[arg-type]
        budget_usd=BUDGET,
        created_at=NOW,
        engine_ref=engine_ref if engine_ref is not None else {},
    )


def ports_with(runs: list[Run]) -> tuple[QueuePorts, FakeWorkflowEngine]:
    engine = FakeWorkflowEngine()
    run_repo = FakeRunRepository(runs)
    steps = FakeStepRunRepository()
    clock = FakeClock(NOW)
    ports = QueuePorts(
        engine=engine,
        runs=run_repo,
        steps=steps,
        clock=clock,
        max_active_runs=2,
    )
    return ports, engine


# --- saved run appears in list_queue ---------------------------------------------------------


def test_saved_run_appears_with_reason_saved_and_null_position() -> None:
    saved = a_run(engine_ref={}, status="queued")
    ports, _ = ports_with([saved])

    view = list_queue(ports)

    assert len(view.items) == 1
    item = view.items[0]
    assert item.run.id == saved.id
    assert item.reason == REASON_SAVED
    assert item.position is None


def test_saved_run_waiting_since_is_run_created_at() -> None:
    saved = a_run(engine_ref={}, status="queued")
    ports, _ = ports_with([saved])

    view = list_queue(ports)

    assert view.items[0].waiting_since == NOW


# --- saved run sorts after engine-queue rows -------------------------------------------------


def test_saved_row_sorts_after_running_row() -> None:
    """A saved run (order key (3, 0)) sorts after a running row (order key (0, 0))."""
    running_row = QueueRow(
        position=None,
        run=a_run(status="running"),
        next_step_label="build",
        reason=REASON_RUNNING,
        waiting_since=NOW,
        waiting_seconds=1.0,
    )
    saved_row = QueueRow(
        position=None,
        run=a_run(engine_ref={}),
        next_step_label="",
        reason=REASON_SAVED,
        waiting_since=NOW,
        waiting_seconds=2.0,
    )

    ordered = sorted([saved_row, running_row], key=_order_key)

    assert ordered[0].reason == REASON_RUNNING
    assert ordered[1].reason == REASON_SAVED


# --- _order_key returns (3, 0) for REASON_SAVED ----------------------------------------------


def test_order_key_for_saved_row_is_3_0() -> None:
    row = QueueRow(
        position=None,
        run=a_run(engine_ref={}),
        next_step_label="",
        reason=REASON_SAVED,
        waiting_since=NOW,
        waiting_seconds=0.0,
    )

    assert _order_key(row) == (3, 0)


# --- normally queued run (engine_ref non-empty) is NOT in saved set --------------------------


def test_normally_queued_run_not_in_saved_set() -> None:
    """A queued run with a non-empty engine_ref is in the engine queue, not the saved set."""
    normal = a_run(engine_ref={"ref": 1}, status="queued")
    ports, engine = ports_with([normal])
    # add the run to the engine's own queue
    engine.enqueue(normal.id, partition_key="repo:branch")

    view = list_queue(ports)

    # The run appears via the engine entry, not as a "saved" row
    assert len(view.items) == 1
    assert view.items[0].reason != REASON_SAVED
