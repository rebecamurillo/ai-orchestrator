"""`record_activity` (SM-2, story 8-2): pure accumulation logic.

The router-level tests (`tests/unit/test_run_activity_router.py`) prove the HTTP boundary;
this module proves the use-case rules: accumulation, return value, and acceptance for any
Run status.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.activity import ActivityPorts, record_activity
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 9, 11, tzinfo=UTC)
BATCH = 45
BATCH_SMALL = 30
DOUBLE_BATCH = BATCH * 2


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def ports_with(run: Run) -> tuple[ActivityPorts, FakeRunRepository]:
    runs = FakeRunRepository([run])
    uow = FakeUnitOfWork()
    uow.__enter__()  # mirrors what the real activity_ports provider does
    return ActivityPorts(runs=runs, uow=uow), runs


def test_accumulation_from_zero() -> None:
    run = a_run(active_seconds=0)
    ports, _ = ports_with(run)

    result = record_activity(ports, run.id, BATCH)

    assert result == BATCH


def test_accumulation_adds_to_existing() -> None:
    run = a_run(active_seconds=BATCH)
    ports, runs = ports_with(run)

    result = record_activity(ports, run.id, BATCH)

    assert result == DOUBLE_BATCH
    assert runs.runs[run.id].active_seconds == DOUBLE_BATCH


def test_any_run_status_accepted() -> None:
    for status in ("done", "failed", "cancelled", "running", "queued", "needs_you"):
        run = a_run(active_seconds=0, status=status)
        ports, _ = ports_with(run)

        result = record_activity(ports, run.id, BATCH_SMALL)

        assert result == BATCH_SMALL, f"expected {BATCH_SMALL} for status {status!r}"


def test_unknown_run_raises_not_found() -> None:
    runs = FakeRunRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()  # mirrors what the real activity_ports provider does
    ports = ActivityPorts(runs=runs, uow=uow)
    unknown_id = new_id()

    with pytest.raises(NotFound):
        record_activity(ports, unknown_id, 30)


def test_active_seconds_is_never_decremented() -> None:
    """Calling record_activity twice accumulates, never resets."""
    run = a_run(active_seconds=0)
    ports, runs = ports_with(run)

    record_activity(ports, run.id, BATCH)

    # Re-read the updated run for the second call
    runs2 = FakeRunRepository([runs.runs[run.id]])
    uow2 = FakeUnitOfWork()
    uow2.__enter__()  # mirrors what the real activity_ports provider does
    ports2 = ActivityPorts(runs=runs2, uow=uow2)
    result = record_activity(ports2, run.id, BATCH)

    assert result == DOUBLE_BATCH
