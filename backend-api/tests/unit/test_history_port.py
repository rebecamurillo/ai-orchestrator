"""The `HistoryQuery` port and the one fake every history test injects (story 7-5, CAP-5).

`GET /steps` is the only read in this system whose unit of iteration is the *attempt* rather
than the Run or the row, and it needs all four entities at once — attempt, `step_run`, `run`,
`project` — in one keyset-ordered answer. That is a query, not four repository reads a use
case could join in Python: joining in `application/` would page over the wrong table (an
attempt's page is not a Run's page) and would read the whole `attempt` table to find one
page of it.

So it is a port of its own, with a fake of its own, rather than a fifth method on
`AttemptRepository` — which already has a fake this story is forbidden to grow a second
double for (root `AGENTS.md` hard rule 6), and whose every other method is keyed by one row.
This module checks the fake structurally against the `Protocol` and then against the four
behaviours the SQLAlchemy adapter's index gives it: the order, the filters, the keyset
window, and the limit.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.history import (
    HistoryCursor,
    HistoryEntry,
    HistoryQuery,
    HistoryQuerySpec,
)
from orchestrator.domain.statuses import StepStatus
from tests.unit.fakes.history import FakeHistoryQuery

AT = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
PROJECT_ID = new_id()
PAGE = 4
ENTRIES = 6


def an_entry(  # noqa: PLR0913 — a fixture builder: one keyword per field a test varies
    *,
    minute: int,
    attempt_id: UUID | None = None,
    project_id: UUID = PROJECT_ID,
    status: StepStatus = "done",
    harness: str | None = "claude",
    started: bool = True,
) -> HistoryEntry:
    run = Run(
        id=new_id(),
        project_id=project_id,
        repository_id=new_id(),
        template_name="story",
        template_version=2,
        status="running",
        budget_usd=Decimal("10.000000"),
        inputs={"base_branch": "main"},
        created_at=AT,
    )
    step = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=7,
        path="epics[0].stories[1].build",
        label="epic 1 · story 1-2 · build",
        kind="agent",
        gate="deterministic",
        status=status,
    )
    attempt = Attempt(
        id=attempt_id or new_id(),
        run_id=run.id,
        step_run_id=step.id,
        n=1,
        status=status,
        started_at=AT + timedelta(minutes=minute) if started else None,
        ended_at=AT + timedelta(minutes=minute + 1) if started else None,
        harness=harness,
    )
    return HistoryEntry(attempt=attempt, step=step, run=run, project_name="acme")


def spec(**overrides: object) -> HistoryQuerySpec:
    fields: dict[str, object] = {"limit": 50}
    fields.update(overrides)
    return HistoryQuerySpec(**fields)  # type: ignore[arg-type]


def test_the_fake_satisfies_the_port() -> None:
    assert isinstance(FakeHistoryQuery(), HistoryQuery)


def test_entries_come_back_newest_first() -> None:
    query = FakeHistoryQuery([an_entry(minute=1), an_entry(minute=9), an_entry(minute=5)])

    minutes = [entry.attempt.started_at for entry in query.list_attempts(spec())]

    assert minutes == [AT + timedelta(minutes=n) for n in (9, 5, 1)]


def test_two_attempts_at_the_same_instant_are_ordered_by_id_descending() -> None:
    low, high = sorted([new_id(), new_id()])
    query = FakeHistoryQuery(
        [an_entry(minute=3, attempt_id=low), an_entry(minute=3, attempt_id=high)]
    )

    ids = [entry.attempt.id for entry in query.list_attempts(spec())]

    assert ids == [high, low]


def test_the_limit_is_the_page_size() -> None:
    query = FakeHistoryQuery([an_entry(minute=n) for n in range(ENTRIES)])

    assert len(query.list_attempts(spec(limit=PAGE))) == PAGE


def test_the_cursor_window_excludes_the_row_it_names() -> None:
    query = FakeHistoryQuery([an_entry(minute=n) for n in (1, 2, 3)])
    second = query.list_attempts(spec())[1]
    after = HistoryCursor(started_at=second.attempt.started_at, attempt_id=second.attempt.id)

    remaining = query.list_attempts(spec(after=after))

    assert [entry.attempt.id for entry in remaining] == [
        entry.attempt.id
        for entry in query.entries
        if entry.attempt.started_at == AT + timedelta(minutes=1)
    ]


def test_the_project_filter_keeps_only_that_projects_attempts() -> None:
    other = new_id()
    query = FakeHistoryQuery([an_entry(minute=1), an_entry(minute=2, project_id=other)])

    kept = query.list_attempts(spec(project_id=other))

    assert [entry.run.project_id for entry in kept] == [other]


def test_the_status_filter_keeps_only_the_listed_statuses() -> None:
    query = FakeHistoryQuery(
        [an_entry(minute=1, status="done"), an_entry(minute=2, status="blocked")]
    )

    kept = query.list_attempts(spec(statuses=("blocked",)))

    assert [entry.attempt.status for entry in kept] == ["blocked"]


def test_the_harness_filter_keeps_only_that_harness() -> None:
    query = FakeHistoryQuery(
        [an_entry(minute=1, harness="codex"), an_entry(minute=2, harness=None)]
    )

    kept = query.list_attempts(spec(harness="codex"))

    assert [entry.attempt.harness for entry in kept] == ["codex"]


def test_every_call_is_recorded_with_the_spec_it_was_made_with() -> None:
    query = FakeHistoryQuery()

    query.list_attempts(spec(limit=3))

    assert query.calls == [spec(limit=3)]


def test_an_attempt_that_never_started_is_not_a_history_row() -> None:
    query = FakeHistoryQuery()

    with pytest.raises(ValueError, match="never started"):
        query.add(an_entry(minute=0, started=False))
