"""`application/use_cases/run_events.py`: the watcher's read model, over the shared fakes.

The point of these is that `admitted_signals` is the *same* list `GET /runs/{id}` offers —
the one list a Signal may be chosen from (SPEC CAP-9) — so a watching agent reading the
events endpoint is never offered a Signal the Run screen would not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_events import run_event
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
WRITTEN_AT = datetime(2026, 10, 1, 9, 5, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-0000000000e1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-0000000000e2")
PARK_PATH = "epics[0].stories[0].steps[2]"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "spend_usd": Decimal("1.5"),
        "inputs": {"base_branch": "main"},
        "created_at": NOW,
        "updated_at": WRITTEN_AT,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run_id: UUID, **overrides: object) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run_id,
        "seq": 1,
        "path": PARK_PATH,
        "label": "implement",
        "kind": "agent",
        "gate": "unvalidated",
        "status": "blocked",
    }
    fields.update(overrides)
    return StepRun(**fields)  # type: ignore[arg-type]


def ports(run: Run, rows: list[StepRun] | None = None) -> RunReadPorts:
    return RunReadPorts(runs=FakeRunRepository([run]), steps=FakeStepRunRepository(rows or []))


def test_a_running_run_reports_its_state_and_the_cancel_it_admits() -> None:
    run = a_run()

    event = run_event(ports(run), run.id)

    assert event.run_id == run.id
    assert event.status == "running"
    assert event.updated_at == WRITTEN_AT
    assert event.spend_usd == Decimal("1.5")
    assert event.budget_usd == Decimal("10")
    assert event.park_kind is None and event.park_path is None
    assert event.admitted_signals == ("cancel",)


def test_a_parked_run_reports_the_park_and_the_signals_that_stop_admits() -> None:
    run = a_run(status="needs_you", park_kind="blocked", park_path=PARK_PATH)

    event = run_event(ports(run, [a_row(run.id)]), run.id)

    assert (event.park_kind, event.park_path) == ("blocked", PARK_PATH)
    assert "answer" in event.admitted_signals
    assert "cancel" in event.admitted_signals


def test_a_terminal_run_admits_nothing_and_still_reports_its_spend() -> None:
    run = a_run(status="done", spend_usd=Decimal("4.25"))

    event = run_event(ports(run), run.id)

    assert event.admitted_signals == ()
    assert event.spend_usd == Decimal("4.25")


def test_a_run_that_has_never_been_written_has_no_updated_at() -> None:
    """Only a fake and a planner hold one; the field is the database's."""
    run = a_run(updated_at=None)

    assert run_event(ports(run), run.id).updated_at is None


def test_an_unknown_id_is_not_found_rather_than_an_empty_answer() -> None:
    run = a_run()

    with pytest.raises(NotFound):
        run_event(ports(run), new_id())
