"""`open_run` (story 8-3): swap `last_opened_before ← last_opened_at`, advance `last_opened_at`.

The router-level tests (`tests/unit/test_run_detail_opened_router.py`) prove the HTTP
boundary; this module proves the use-case rules: the swap semantics on first and second open,
and the 404 on an unknown run_id.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.open_run import OpenRunPorts, open_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.runs import FakeRunRepository

T1 = datetime(2026, 9, 11, 10, 0, 0, tzinfo=UTC)
T2 = datetime(2026, 9, 11, 12, 0, 0, tzinfo=UTC)
T3 = datetime(2026, 9, 11, 14, 0, 0, tzinfo=UTC)

_OTHER_ACTIVE_SECONDS = 99


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": "main"},
        "created_at": T1,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def ports_with(run: Run, now: datetime) -> tuple[OpenRunPorts, FakeRunRepository]:
    runs = FakeRunRepository([run])
    uow = FakeUnitOfWork()
    clock = FakeClock(now)
    return OpenRunPorts(runs=runs, uow=uow, clock=clock), runs


def test_first_open_sets_last_opened_at_and_leaves_last_opened_before_none() -> None:
    """First open: `last_opened_at=null` → `last_opened_at=now`, `last_opened_before=null`."""
    run = a_run(last_opened_at=None)
    ports, runs = ports_with(run, T2)

    open_run(ports, run.id)

    updated = runs.runs[run.id]
    assert updated.last_opened_at == T2
    assert updated.last_opened_before is None


def test_second_open_swaps_before_and_advances_at() -> None:
    """Second open: `last_opened_before ← last_opened_at`, `last_opened_at = now`."""
    run = a_run(last_opened_at=T1, last_opened_before=None)
    ports, runs = ports_with(run, T2)

    open_run(ports, run.id)

    updated = runs.runs[run.id]
    assert updated.last_opened_at == T2
    assert updated.last_opened_before == T1


def test_third_open_advances_both_fields() -> None:
    """Third open: prior `last_opened_at` becomes `last_opened_before`."""
    run = a_run(last_opened_at=T2, last_opened_before=T1)
    ports, runs = ports_with(run, T3)

    open_run(ports, run.id)

    updated = runs.runs[run.id]
    assert updated.last_opened_at == T3
    assert updated.last_opened_before == T2


def test_open_run_commits_the_unit_of_work() -> None:
    run = a_run()
    uow = FakeUnitOfWork()
    runs = FakeRunRepository([run])
    clock = FakeClock(T2)
    ports = OpenRunPorts(runs=runs, uow=uow, clock=clock)

    open_run(ports, run.id)

    assert uow.committed


def test_open_run_calls_update_on_the_repository() -> None:
    run = a_run()
    ports, runs = ports_with(run, T2)

    open_run(ports, run.id)

    method_names = [call[0] for call in runs.calls]
    assert "update" in method_names


def test_unknown_run_id_raises_not_found() -> None:
    runs = FakeRunRepository()
    uow = FakeUnitOfWork()
    clock = FakeClock(T2)
    ports = OpenRunPorts(runs=runs, uow=uow, clock=clock)

    with pytest.raises(NotFound):
        open_run(ports, new_id())


def test_other_run_fields_are_unchanged() -> None:
    """Only `last_opened_at` and `last_opened_before` change; every other field is stable."""
    run = a_run(last_opened_at=T1, active_seconds=_OTHER_ACTIVE_SECONDS, status="running")
    ports, runs = ports_with(run, T2)

    open_run(ports, run.id)

    updated = runs.runs[run.id]
    assert updated.active_seconds == _OTHER_ACTIVE_SECONDS
    assert updated.status == "running"
    assert updated.id == run.id
