"""How `RealEngine.schedule` registers a recurring job, and why it is `apply_schedules`.

`tests/unit/test_dbos_facade.py` pins the library's surface symbol by symbol; this module
pins the one call whose *choice* carries a rule, because the wrong choice does not fail
until the second time the process starts.

A DBOS schedule is a row in the system database, keyed by name, and the system database
outlives the process. `DBOS.create_schedule` refuses a name it already holds — so a backend
that registered `clone_check` once crashes on start-up every time afterwards, never binds
its socket, and cannot be restarted against any database it has already run against. That is
what `tests/e2e/test_durability.py` found the first time anything in this repository started
a second process against a live one. `DBOS.apply_schedules` creates or replaces instead, so
the definition in the source is the one that is stored, however many processes stored it
before.

The library is exercised through `facade.DBOS` here rather than launched: launching needs a
Postgres and belongs to the e2e gate, and what is under test is which call the adapter makes
and with what, not what the engine does with it.
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Any

import pytest
from dbos import DBOS, ScheduleInput

from orchestrator.infrastructure.dbos import facade
from orchestrator.infrastructure.dbos.facade import RealEngine

CRON = "0 0 3 * * *"
NAME = "clone_check"

#: What the scheduler calls a workflow back with; the wrapper's job is to absorb both.
_AN_INSTANT = datetime(2026, 9, 7, tzinfo=UTC)


def test_the_library_still_offers_the_create_or_replace_call_the_facade_makes() -> None:
    """The day a `dbos` upgrade drops it, the failure is this line — not a Run that never
    starts, and not a backend that will not come back up."""
    assert hasattr(DBOS, "apply_schedules"), "dbos no longer exposes DBOS.apply_schedules"
    assert "schedules" in inspect.signature(DBOS.apply_schedules).parameters


def test_the_library_still_takes_the_three_keys_the_facade_writes() -> None:
    """`ScheduleInput` is a `TypedDict`, so a renamed key is a silent no-op at runtime rather
    than a `TypeError`; naming the three here is what turns that into a failed gate."""
    assert set(ScheduleInput.__annotations__) >= {"schedule_name", "workflow_fn", "schedule"}


@pytest.fixture
def applied(monkeypatch: pytest.MonkeyPatch) -> list[list[dict[str, Any]]]:
    """Every `apply_schedules` call the facade makes, with the workflow declaration stubbed."""
    calls: list[list[dict[str, Any]]] = []
    monkeypatch.setattr(facade.DBOS, "workflow", lambda **kwargs: lambda function: function)
    monkeypatch.setattr(facade.DBOS, "apply_schedules", calls.append)
    monkeypatch.setattr(facade.DBOS, "create_schedule", _refused)
    return calls


def _refused(**keywords: object) -> None:
    """The call the facade must not make. Registering a schedule with it crashes every start-up
    after the first, which is the defect this module exists to keep fixed."""
    raise AssertionError("the facade called DBOS.create_schedule, which refuses an existing name")


def test_a_schedule_is_registered_by_create_or_replace_not_by_create(
    applied: list[list[dict[str, Any]]],
) -> None:
    RealEngine().schedule(NAME, CRON, lambda: None)

    assert len(applied) == 1
    (entry,) = applied[0]
    assert entry["schedule_name"] == NAME
    assert entry["schedule"] == CRON


def test_registering_the_same_schedule_again_is_the_same_call_and_not_a_failure(
    applied: list[list[dict[str, Any]]],
) -> None:
    """A restart re-registers every job; that must be a replacement, never a refusal."""
    engine = RealEngine()

    engine.schedule(NAME, CRON, lambda: None)
    engine.schedule(NAME, CRON, lambda: None)

    assert [entry["schedule_name"] for call in applied for entry in call] == [NAME, NAME]


def test_the_registered_workflow_runs_the_job_it_was_given(
    applied: list[list[dict[str, Any]]],
) -> None:
    """The scheduler calls back with two datetimes the job does not take; the wrapper is what
    absorbs them, and it is the only thing between the cron row and `scheduled_jobs`."""
    fired: list[int] = []

    RealEngine().schedule(NAME, CRON, lambda: fired.append(1))
    (entry,) = applied[0]
    entry["workflow_fn"](_AN_INSTANT, _AN_INSTANT)

    assert fired == [1]
