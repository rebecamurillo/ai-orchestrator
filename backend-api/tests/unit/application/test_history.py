"""`list_history` (SPEC CAP-5, FR-25 history): one row per attempt, newest first, paged.

The Runs screen's HISTORY table asks a question no other read model answers: *what has
actually executed, across every Run?* Every other read is scoped to one Run (the detail),
one Project (the Board), or the engine's own holding pen (the queue). This one iterates
attempts, so its page is a page of attempts and its cursor is an attempt's own keyset.

What this module pins:

- the order and the paging — `started_at desc, attempt_id desc`, an opaque cursor, and a
  last page whose `next_cursor` is `None`;
- the filters — the bar's project filter, its status tokens, and the harness name the
  comparison this epic exists for is read by;
- what a row reports and what it does not derive (AD-8): `status` is the attempt's own
  stored status and `token` is `application/graph.py::STEP_TOKENS`'s existing mapping of it,
  never a status this module computes.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.application.use_cases.history import (
    DEFAULT_LIMIT,
    STATUS_FILTERS,
    HistoryFilters,
    HistoryPorts,
    list_history,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import Invalid
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.history import HistoryEntry
from orchestrator.domain.statuses import StepStatus
from tests.unit.fakes.history import FakeHistoryQuery
from tests.unit.fakes.tracer import FakeTracer

AT = datetime(2026, 9, 9, 8, 0, tzinfo=UTC)
PROJECT_ID = new_id()

#: The brief's own first acceptance, as figures: ten attempts, read `limit=5` twice.
ATTEMPTS = 10
PAGE = 5
#: The other page sizes and durations these tests assert on, named so `PLR2004` can hold.
THREE_ROWS = 3
FOUR_ROWS = 4
ATTEMPT_SECONDS = 30.0


def an_entry(  # noqa: PLR0913 — a fixture builder: one keyword per field a test varies
    *,
    minute: int,
    project_id: UUID = PROJECT_ID,
    project_name: str = "acme",
    status: StepStatus = "done",
    kind: str = "agent",
    harness: str | None = "claude",
    trace_id: str | None = None,
    ended: bool = True,
) -> HistoryEntry:
    agent = kind == "agent"
    run = Run(
        id=new_id(),
        project_id=project_id,
        repository_id=new_id(),
        template_name="story",
        template_version=3,
        status="running",
        budget_usd=Decimal("10.000000"),
        inputs={"base_branch": "feat/epic-7"},
        created_at=AT,
        trace_id=trace_id,
    )
    step = StepRun(
        id=new_id(),
        run_id=run.id,
        seq=minute,
        path=f"epics[0].stories[{minute}].build",
        label="build",
        kind=kind,
        gate="deterministic",
        status=status,
    )
    attempt = Attempt(
        id=new_id(),
        run_id=run.id,
        step_run_id=step.id,
        n=1,
        status=status,
        started_at=AT + timedelta(minutes=minute),
        ended_at=AT + timedelta(minutes=minute, seconds=30) if ended else None,
        harness=harness if agent else None,
        model="sonnet" if agent else None,
        session_id="sess-1" if agent else None,
        tokens_in=1200 if agent else None,
        tokens_out=340 if agent else None,
        cost_usd=Decimal("0.250000") if agent else None,
        cost_provisional=agent,
    )
    return HistoryEntry(attempt=attempt, step=step, run=run, project_name=project_name)


def ports(entries: list[HistoryEntry], *, tracer: FakeTracer | None = None) -> HistoryPorts:
    return HistoryPorts(history=FakeHistoryQuery(entries), tracer=tracer)


# ── order, paging, the cursor ─────────────────────────────────────────────────


def test_rows_arrive_newest_first() -> None:
    page = list_history(ports([an_entry(minute=n) for n in (1, 7, 4)]))

    assert [row.started_at for row in page.items] == [AT + timedelta(minutes=n) for n in (7, 4, 1)]


def test_ten_attempts_read_two_pages_of_five_then_an_empty_third() -> None:
    """The brief's first acceptance, over agent and non-agent rows alike."""
    entries = [an_entry(minute=n, kind="agent" if n % 2 else "git.commit") for n in range(10)]
    port = ports(entries)

    first = list_history(port, HistoryFilters(limit=PAGE))
    second = list_history(port, HistoryFilters(limit=PAGE, cursor=first.next_cursor))
    third = list_history(port, HistoryFilters(limit=PAGE, cursor=second.next_cursor))

    seen = [row.attempt_id for row in first.items + second.items]
    assert len(first.items) == len(second.items) == PAGE
    assert len(set(seen)) == ATTEMPTS
    assert third.items == []
    assert third.next_cursor is None


def test_a_short_page_is_the_end_and_says_so() -> None:
    page = list_history(
        ports([an_entry(minute=n) for n in range(THREE_ROWS)]), HistoryFilters(limit=FOUR_ROWS)
    )

    assert len(page.items) == THREE_ROWS
    assert page.next_cursor is None


def test_a_full_page_carries_a_cursor_even_when_nothing_follows_it() -> None:
    """The brief's own acceptance: the end is proved by an *empty* page, not by a short one.

    See `list_history`'s docstring for the trade this makes against a `limit + 1` look-ahead.
    """
    port = ports([an_entry(minute=n) for n in range(FOUR_ROWS)])

    full = list_history(port, HistoryFilters(limit=FOUR_ROWS))
    after = list_history(port, HistoryFilters(limit=FOUR_ROWS, cursor=full.next_cursor))

    assert full.next_cursor is not None
    assert after.items == []
    assert after.next_cursor is None


def test_an_unreadable_cursor_is_refused_rather_than_ignored() -> None:
    with pytest.raises(Invalid, match="cursor"):
        list_history(ports([]), HistoryFilters(cursor="not-a-cursor"))


def test_a_cursor_that_decodes_to_the_wrong_shape_is_refused() -> None:
    forged = urlsafe_b64encode(b"2026-09-09T08:00:00+00:00").decode()

    with pytest.raises(Invalid, match="cursor"):
        list_history(ports([]), HistoryFilters(cursor=forged))


def test_the_default_page_size_is_the_briefs_fifty() -> None:
    port = FakeHistoryQuery()

    list_history(HistoryPorts(history=port))

    assert port.calls[0].limit == DEFAULT_LIMIT


# ── the filters ───────────────────────────────────────────────────────────────


def test_the_project_filter_reaches_the_query() -> None:
    other = new_id()
    page = list_history(
        ports([an_entry(minute=1), an_entry(minute=2, project_id=other, project_name="beta")]),
        HistoryFilters(project_id=other),
    )

    assert [row.project_name for row in page.items] == ["beta"]


def test_the_blocked_token_selects_the_two_ways_a_row_stops_short() -> None:
    entries = [
        an_entry(minute=1, status="blocked"),
        an_entry(minute=2, status="error"),
        an_entry(minute=3, status="done"),
    ]

    page = list_history(ports(entries), HistoryFilters(status="BLK"))

    assert sorted(row.status for row in page.items) == ["blocked", "error"]


def test_the_error_token_narrows_to_the_errored_attempts_alone() -> None:
    entries = [an_entry(minute=1, status="blocked"), an_entry(minute=2, status="error")]

    page = list_history(ports(entries), HistoryFilters(status="ERR"))

    assert [row.status for row in page.items] == ["error"]


@pytest.mark.parametrize("token", sorted(STATUS_FILTERS))
def test_every_offered_token_is_accepted(token: str) -> None:
    assert list_history(ports([]), HistoryFilters(status=token)).items == []


def test_an_unknown_status_token_is_refused() -> None:
    with pytest.raises(Invalid, match="status"):
        list_history(ports([]), HistoryFilters(status="NOPE"))


def test_the_harness_filter_reaches_the_query() -> None:
    entries = [an_entry(minute=1, harness="codex"), an_entry(minute=2, harness="claude")]

    page = list_history(ports(entries), HistoryFilters(harness="codex"))

    assert [row.harness for row in page.items] == ["codex"]


# ── what a row reports ────────────────────────────────────────────────────────


def test_an_agent_row_carries_the_harness_the_session_the_tokens_and_the_cost() -> None:
    row = list_history(ports([an_entry(minute=1)])).items[0]

    assert (row.harness, row.model, row.session_id) == ("claude", "sonnet", "sess-1")
    assert (row.tokens_in, row.tokens_out) == (1200, 340)
    assert row.cost_usd == Decimal("0.250000")
    assert row.cost_provisional is True


def test_a_non_agent_row_carries_nulls_for_all_of_them() -> None:
    row = list_history(ports([an_entry(minute=1, kind="git.commit")])).items[0]

    assert (row.harness, row.model, row.session_id) == (None, None, None)
    assert (row.tokens_in, row.tokens_out, row.cost_usd) == (None, None, None)
    assert row.kind == "git.commit"


def test_the_row_states_the_stored_status_and_its_existing_token() -> None:
    row = list_history(ports([an_entry(minute=1, status="checkpoint")])).items[0]

    assert (row.status, row.token) == ("checkpoint", "CHK")


def test_the_workflow_label_is_the_template_its_version_and_the_branch() -> None:
    row = list_history(ports([an_entry(minute=1)])).items[0]

    assert row.run_label == "story v3 · feat/epic-7"


def test_the_path_and_the_sequence_are_both_carried_so_the_row_can_link_to_it() -> None:
    row = list_history(ports([an_entry(minute=4)])).items[0]

    assert row.path == "epics[0].stories[4].build"
    assert row.seq == FOUR_ROWS


def test_a_finished_attempt_reports_the_seconds_it_took() -> None:
    row = list_history(ports([an_entry(minute=1)])).items[0]

    assert row.seconds == ATTEMPT_SECONDS


def test_an_attempt_still_running_reports_no_end_and_no_duration() -> None:
    row = list_history(ports([an_entry(minute=1, ended=False, status="running")])).items[0]

    assert (row.ended_at, row.seconds) == (None, None)


def test_the_trace_link_is_the_runs_own_trace_because_no_attempt_trace_is_stored() -> None:
    tracer = FakeTracer()
    page = list_history(ports([an_entry(minute=1, trace_id="tr-9")], tracer=tracer))

    assert page.items[0].trace_url == tracer.trace_url("tr-9")


def test_a_run_with_no_trace_has_no_trace_link() -> None:
    page = list_history(ports([an_entry(minute=1)], tracer=FakeTracer()))

    assert page.items[0].trace_url is None


def test_without_a_tracer_wired_no_row_claims_a_trace_link() -> None:
    page = list_history(ports([an_entry(minute=1, trace_id="tr-9")]))

    assert page.items[0].trace_url is None


def test_the_log_tail_link_is_the_run_detail_read_that_actually_serves_one() -> None:
    row = list_history(ports([an_entry(minute=1)])).items[0]

    assert row.log_tail_url == f"/api/v1/runs/{row.run_id}/detail"


def test_an_attempt_that_never_started_is_not_printed_as_a_row() -> None:
    """The port promises it never answers one; this is the guard that keeps that checkable.

    Pushed past `FakeHistoryQuery.add`, which refuses it, straight onto the list the fake
    answers from — the point is what `list_history` does with an entry the port should never
    have handed it, not what the fake accepts.
    """
    port = FakeHistoryQuery([an_entry(minute=1)])
    unstarted = an_entry(minute=2)
    port.entries.append(
        HistoryEntry(
            attempt=unstarted.attempt.model_copy(update={"started_at": None}),
            step=unstarted.step,
            run=unstarted.run,
            project_name=unstarted.project_name,
        )
    )

    page = list_history(HistoryPorts(history=port))

    assert [row.seq for row in page.items] == [1]
