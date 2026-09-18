"""`list_queue` with saved Runs (story 5-3): a saved Run appears with `reason="saved — not
started"` and `position=None`.

A saved Run has `status="queued"` and `engine_ref={}`. It is NOT in the engine's own queue
(it was never enqueued), so it does not appear via `engine.list_queue()`. `list_queue`
queries `runs.list_by_status("queued")`, filters to those with an empty `engine_ref`, and
appends them after the engine-queue rows before sorting.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from orchestrator.application.use_cases.queue import (
    REASON_SAVED,
    QueuePorts,
    list_queue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)
PROJECT = new_id()
REPOSITORY = new_id()


def _run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT,
        "repository_id": REPOSITORY,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "queued",
        "engine_ref": {},
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW - timedelta(minutes=5),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def _ports(runs: FakeRunRepository, engine: FakeWorkflowEngine) -> QueuePorts:
    return QueuePorts(
        engine=engine,
        runs=runs,
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=2,
    )


# ── saved run appears in the queue ───────────────────────────────────────────────────────────


def test_saved_run_appears_with_reason_saved() -> None:
    run = _run()
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _ports(runs, engine)

    view = list_queue(ports)

    reasons = [row.reason for row in view.items]
    assert REASON_SAVED in reasons


def test_saved_run_reason_is_the_constant_string() -> None:
    assert REASON_SAVED == "saved — not started"


def test_saved_run_has_position_none() -> None:
    run = _run()
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _ports(runs, engine)

    view = list_queue(ports)

    saved_row = next(r for r in view.items if r.reason == REASON_SAVED)
    assert saved_row.position is None


def test_saved_run_waiting_since_is_created_at() -> None:
    run = _run()
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _ports(runs, engine)

    view = list_queue(ports)

    saved_row = next(r for r in view.items if r.reason == REASON_SAVED)
    assert saved_row.waiting_since == run.created_at


def test_saved_run_waiting_seconds_is_elapsed() -> None:
    run = _run()
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _ports(runs, engine)

    view = list_queue(ports)

    saved_row = next(r for r in view.items if r.reason == REASON_SAVED)
    expected = (NOW - run.created_at).total_seconds()
    assert saved_row.waiting_seconds == expected


# ── enqueued run is not duplicated ───────────────────────────────────────────────────────────


def test_enqueued_run_with_engine_ref_not_in_saved_rows() -> None:
    """A Run with a non-empty engine_ref is in the engine queue already; don't double-count."""
    enqueued_run = _run(engine_ref={"ref": 1}, status="queued")
    runs = FakeRunRepository([enqueued_run])
    engine = FakeWorkflowEngine()
    # put it in the engine queue
    engine.enqueue(enqueued_run.id, partition_key="x")
    # FakeWorkflowEngine.enqueue does not add the run to the engine's internal queue
    # by run_id lookup — but we clear calls to test the saved-path logic
    engine.calls.clear()
    ports = _ports(runs, engine)

    view = list_queue(ports)

    saved_reasons = [r.reason for r in view.items if r.reason == REASON_SAVED]
    assert saved_reasons == []
