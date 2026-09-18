"""Queue view for dependency-waiting Runs (story 5-4).

`_saved_row` uses `REASON_WAITING_DEPENDENCY` when a saved Run has `after_run_id` set.
`_order_key` buckets both `REASON_SAVED` and `"waiting for run …"` at (3, 0).

Coverage:
- A saved Run with `after_run_id` → reason = `"waiting for run <uuid>"`
- A saved Run without `after_run_id` → reason = `"saved — not started"`
- `_order_key` sorts dependency-waiting rows at bucket 3 (after parked rows at 2)
"""

from __future__ import annotations

from orchestrator.application.use_cases.queue import (
    REASON_SAVED,
    REASON_WAITING_DEPENDENCY,
    QueuePorts,
    QueueRow,
    _order_key,
    _saved_row,
    list_queue,
)
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import build_run
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeRunRepository,
    FakeStepRunRepository,
)


def _queue_ports(runs, *, engine=None):
    clock = FakeClock()
    uow = FakeUnitOfWork()
    eng = engine or FakeWorkflowEngine(clock=clock, uow=uow)
    return QueuePorts(
        runs=runs,
        steps=FakeStepRunRepository(),
        engine=eng,
        clock=clock,
        max_active_runs=5,
    )


# ── _saved_row reason ─────────────────────────────────────────────────────────


def test_saved_row_with_after_run_id_uses_waiting_dependency_reason() -> None:
    """A saved Run with after_run_id shows the dependency-waiting reason."""
    predecessor_id = new_id()
    run = build_run(status="queued", after_run_id=predecessor_id, engine_ref={})
    ports = _queue_ports(FakeRunRepository([run]))

    row = _saved_row(ports, run)

    expected = REASON_WAITING_DEPENDENCY.format(x=str(predecessor_id))
    assert row.reason == expected


def test_saved_row_without_after_run_id_uses_saved_reason() -> None:
    """A saved Run without after_run_id shows the plain 'saved' reason."""
    run = build_run(status="queued", engine_ref={})
    ports = _queue_ports(FakeRunRepository([run]))

    row = _saved_row(ports, run)

    assert row.reason == REASON_SAVED


# ── _order_key bucketing ──────────────────────────────────────────────────────


def _make_row(reason: str, position=None) -> QueueRow:
    """Minimal QueueRow for testing _order_key."""
    run = build_run(status="queued", engine_ref={})
    return QueueRow(
        position=position,
        run=run,
        next_step_label="plan",
        reason=reason,
        waiting_since=EPOCH,
        waiting_seconds=0.0,
    )


def test_order_key_for_dependency_waiting_is_bucket_3() -> None:
    """A dependency-waiting row sorts at (3, 0) — same as a plain saved row."""
    predecessor_id = new_id()
    reason = REASON_WAITING_DEPENDENCY.format(x=str(predecessor_id))
    row = _make_row(reason)
    assert _order_key(row) == (3, 0)


def test_order_key_for_plain_saved_is_bucket_3() -> None:
    """A plain saved row sorts at (3, 0)."""
    row = _make_row(REASON_SAVED)
    assert _order_key(row) == (3, 0)


def test_order_key_dependency_waiting_after_parked_rows() -> None:
    """A dependency-waiting row sorts after a parked row (bucket 2) but before nothing."""
    predecessor_id = new_id()
    waiting_reason = REASON_WAITING_DEPENDENCY.format(x=str(predecessor_id))
    dependency_row = _make_row(waiting_reason)
    parked_row = _make_row("waiting for your answer")

    assert _order_key(dependency_row) > _order_key(parked_row)


# ── list_queue integration ───────────────────────────────────────────────────


def test_list_queue_includes_dependency_waiting_run() -> None:
    """A saved Run with after_run_id appears in the queue view."""
    predecessor_id = new_id()
    run = build_run(status="queued", after_run_id=predecessor_id, engine_ref={})
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _queue_ports(runs, engine=engine)

    view = list_queue(ports)

    ids = [row.run.id for row in view.items]
    assert run.id in ids


def test_list_queue_dependency_waiting_reason_matches_expected() -> None:
    """The reason string in the queue view includes the predecessor UUID."""
    predecessor_id = new_id()
    run = build_run(status="queued", after_run_id=predecessor_id, engine_ref={})
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _queue_ports(runs, engine=engine)

    view = list_queue(ports)

    rows = [row for row in view.items if row.run.id == run.id]
    assert rows
    expected = REASON_WAITING_DEPENDENCY.format(x=str(predecessor_id))
    assert rows[0].reason == expected
