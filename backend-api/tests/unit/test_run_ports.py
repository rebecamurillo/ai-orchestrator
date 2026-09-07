"""The four Run repository ports and the fakes every Epic 4 use-case test will inject.

A fake that drifted from its port would make every later use-case test a test of the fake,
so each is checked structurally against its `Protocol` and then against the behaviour AD-8's
writers are entitled to assume: ordering that matches the index, a `None` for what is not
stored, a `ValueError` where the unique index would raise, and a `calls` list that records
which repository call was made — the evidence that a transition landed in the unit of work
it was supposed to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.statuses import RunStatus
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

AT = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)
PROJECT_ID = new_id()
REPOSITORY_ID = new_id()


def a_run(
    *,
    project_id: UUID = PROJECT_ID,
    repository_id: UUID = REPOSITORY_ID,
    status: RunStatus = "queued",
    created_at: datetime = AT,
) -> Run:
    return Run(
        id=new_id(),
        project_id=project_id,
        repository_id=repository_id,
        template_name="story",
        template_version=1,
        status=status,
        budget_usd=Decimal("10.000000"),
        created_at=created_at,
    )


def a_step(run_id: UUID, seq: int, *, path: str | None = None, status: str = "planned") -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id,
        seq=seq,
        path=path or f"steps[{seq}]",
        label=f"step {seq}",
        kind="shell",
        gate="deterministic",
        status=status,  # type: ignore[arg-type]
    )


def an_attempt(run_id: UUID, step_run_id: UUID, n: int) -> Attempt:
    return Attempt(id=new_id(), run_id=run_id, step_run_id=step_run_id, n=n, status="running")


def a_record(run_id: UUID, at: datetime, event: str = "start") -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=run_id,
        at=at,
        event=event,  # type: ignore[arg-type]
        actor="machine",
        text="",
    )


# ── the fakes satisfy the ports ──────────────────────────────────────────────


def test_the_run_fake_satisfies_the_port() -> None:
    runs: RunRepository = FakeRunRepository()

    assert isinstance(runs, RunRepository)


def test_the_step_run_fake_satisfies_the_port() -> None:
    steps: StepRunRepository = FakeStepRunRepository()

    assert isinstance(steps, StepRunRepository)


def test_the_attempt_fake_satisfies_the_port() -> None:
    attempts: AttemptRepository = FakeAttemptRepository()

    assert isinstance(attempts, AttemptRepository)


def test_the_gate_record_fake_satisfies_the_port() -> None:
    records: GateRecordRepository = FakeGateRecordRepository()

    assert isinstance(records, GateRecordRepository)


# ── RunRepository ────────────────────────────────────────────────────────────


def test_a_run_round_trips_through_add_and_get() -> None:
    run = a_run()
    runs = FakeRunRepository([run])

    assert runs.get(run.id) == run


def test_an_unstored_run_id_reads_none() -> None:
    assert FakeRunRepository().get(new_id()) is None


def test_update_stores_the_changed_spend_and_estimate() -> None:
    run = a_run()
    runs = FakeRunRepository([run])

    changed = run.model_copy(
        update={"spend_usd": Decimal("2.500000"), "manual_estimate_h": Decimal("1.50")}
    )
    runs.update(changed)

    stored = runs.get(run.id)
    assert stored is not None
    assert stored.spend_usd == Decimal("2.500000")
    assert stored.manual_estimate_h == Decimal("1.50")


def test_update_records_the_call_it_was_asked_to_make() -> None:
    run = a_run()
    runs = FakeRunRepository([run])

    runs.update(run)

    assert ("update", run.id) in runs.calls


def test_every_read_is_recorded_too() -> None:
    runs = FakeRunRepository()
    run_id = new_id()

    runs.get(run_id)
    runs.list()
    runs.list_by_status("running")

    assert runs.calls == [("get", run_id), ("list", None), ("list_by_status", "running")]


def test_adding_a_run_twice_is_refused_the_way_the_primary_key_refuses_it() -> None:
    run = a_run()
    runs = FakeRunRepository([run])

    with pytest.raises(ValueError, match="already stored"):
        runs.add(run)


def test_updating_a_run_that_was_never_stored_is_refused() -> None:
    runs = FakeRunRepository()

    with pytest.raises(ValueError, match="no run with id"):
        runs.update(a_run())


def test_list_is_newest_first() -> None:
    older = a_run(created_at=AT)
    newer = a_run(created_at=AT + timedelta(minutes=1))
    runs = FakeRunRepository([older, newer])

    assert runs.list() == [newer, older]


def test_list_filters_by_project_when_asked() -> None:
    mine = a_run()
    other = a_run(project_id=new_id())
    runs = FakeRunRepository([mine, other])

    assert runs.list(project_id=PROJECT_ID) == [mine]
    assert len(runs.list()) == len([mine, other])


def test_list_by_status_holds_only_that_status() -> None:
    running = a_run(status="running")
    runs = FakeRunRepository([running, a_run(status="done")])

    assert runs.list_by_status("running") == [running]


def test_list_by_repository_non_terminal_leaves_out_the_finished_runs() -> None:
    live = a_run(status="needs_you")
    runs = FakeRunRepository(
        [live, a_run(status="done"), a_run(status="failed"), a_run(status="cancelled")]
    )

    assert runs.list_by_repository_non_terminal(REPOSITORY_ID) == [live]


def test_list_by_repository_non_terminal_is_scoped_to_that_repository() -> None:
    runs = FakeRunRepository([a_run(status="running", repository_id=new_id())])

    assert runs.list_by_repository_non_terminal(REPOSITORY_ID) == []


# ── StepRunRepository ────────────────────────────────────────────────────────


def test_rows_are_added_in_one_call_and_read_back_by_seq() -> None:
    run_id = new_id()
    first, second = a_step(run_id, 1), a_step(run_id, 2)
    steps = FakeStepRunRepository([first, second])

    assert steps.get_by_seq(run_id, 2) == second


def test_an_unknown_seq_reads_none() -> None:
    steps = FakeStepRunRepository()

    assert steps.get_by_seq(new_id(), 1) is None


def test_list_for_run_is_ordered_by_seq_however_the_rows_arrived() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository([a_step(run_id, 3), a_step(run_id, 1), a_step(run_id, 2)])

    assert [row.seq for row in steps.list_for_run(run_id)] == [1, 2, 3]


def test_list_for_run_is_scoped_to_one_run() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository([a_step(run_id, 1), a_step(new_id(), 1)])

    assert len(steps.list_for_run(run_id)) == 1


def test_a_second_row_at_the_same_seq_is_refused_the_way_the_index_refuses_it() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository([a_step(run_id, 1)])

    with pytest.raises(ValueError, match="already has a row at seq"):
        steps.add_many([a_step(run_id, 1, path="steps[9]")])


def test_a_second_row_at_the_same_path_is_refused_too() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository([a_step(run_id, 1)])

    with pytest.raises(ValueError, match="already has a row at"):
        steps.add_many([a_step(run_id, 2, path="steps[1]")])


def test_the_same_seq_under_a_different_run_is_accepted() -> None:
    steps = FakeStepRunRepository([a_step(new_id(), 1)])

    steps.add_many([a_step(new_id(), 1)])

    assert len(steps.steps) == 2  # noqa: PLR2004 — two runs, one row each


def test_adding_the_same_row_id_twice_is_refused() -> None:
    row = a_step(new_id(), 1)
    steps = FakeStepRunRepository([row])

    with pytest.raises(ValueError, match="already stored"):
        steps.add_many([row])


def test_updating_a_row_that_was_never_stored_is_refused() -> None:
    steps = FakeStepRunRepository()

    with pytest.raises(ValueError, match="no step run with id"):
        steps.update(a_step(new_id(), 1))


def test_update_replaces_the_stored_row() -> None:
    run_id = new_id()
    row = a_step(run_id, 1)
    steps = FakeStepRunRepository([row])

    steps.update(row.model_copy(update={"status": "running"}))

    stored = steps.get_by_seq(run_id, 1)
    assert stored is not None
    assert stored.status == "running"


def test_first_queued_is_the_lowest_queued_seq() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository(
        [
            a_step(run_id, 1, status="done"),
            a_step(run_id, 3, status="queued"),
            a_step(run_id, 2, status="queued"),
        ]
    )

    row = steps.first_queued(run_id)

    assert row is not None
    assert row.seq == 2  # noqa: PLR2004 — the seq under test


def test_first_queued_is_none_when_nothing_is_waiting() -> None:
    run_id = new_id()
    steps = FakeStepRunRepository([a_step(run_id, 1, status="running")])

    assert steps.first_queued(run_id) is None


def test_the_step_fake_records_every_call() -> None:
    run_id = new_id()
    row = a_step(run_id, 1)
    steps = FakeStepRunRepository()

    steps.add_many([row])
    steps.list_for_run(run_id)
    steps.first_queued(run_id)

    assert steps.calls == [
        ("add_many", (row.id,)),
        ("list_for_run", run_id),
        ("first_queued", run_id),
    ]


# ── AttemptRepository ────────────────────────────────────────────────────────


def test_attempts_are_listed_for_one_row_in_n_order() -> None:
    run_id, row_id = new_id(), new_id()
    attempts = FakeAttemptRepository([an_attempt(run_id, row_id, 2), an_attempt(run_id, row_id, 1)])

    assert [a.n for a in attempts.list_for_row(row_id)] == [1, 2]


def test_list_for_row_is_scoped_to_that_row() -> None:
    run_id = new_id()
    attempts = FakeAttemptRepository([an_attempt(run_id, new_id(), 1)])

    assert attempts.list_for_row(new_id()) == []


def test_get_latest_is_the_highest_n() -> None:
    run_id, row_id = new_id(), new_id()
    latest = an_attempt(run_id, row_id, 2)
    attempts = FakeAttemptRepository([an_attempt(run_id, row_id, 1), latest])

    assert attempts.get_latest(row_id) == latest


def test_get_latest_is_none_for_a_row_that_never_ran() -> None:
    assert FakeAttemptRepository().get_latest(new_id()) is None


def test_a_second_attempt_at_the_same_n_is_refused_the_way_the_index_refuses_it() -> None:
    run_id, row_id = new_id(), new_id()
    attempts = FakeAttemptRepository([an_attempt(run_id, row_id, 1)])

    with pytest.raises(ValueError, match="already has attempt"):
        attempts.add(an_attempt(run_id, row_id, 1))


def test_the_same_n_under_a_different_row_is_accepted() -> None:
    run_id = new_id()
    attempts = FakeAttemptRepository([an_attempt(run_id, new_id(), 1)])

    attempts.add(an_attempt(run_id, new_id(), 1))

    assert len(attempts.attempts) == 2  # noqa: PLR2004 — two rows, one attempt each


def test_adding_the_same_attempt_id_twice_is_refused() -> None:
    attempt = an_attempt(new_id(), new_id(), 1)
    attempts = FakeAttemptRepository([attempt])

    with pytest.raises(ValueError, match="already stored"):
        attempts.add(attempt)


def test_mark_started_stores_the_half_a_restart_has_to_find() -> None:
    attempt = an_attempt(new_id(), new_id(), 1)
    attempts = FakeAttemptRepository([attempt])

    attempts.mark_started(
        attempt.model_copy(update={"start_sha": "abc", "pgid": 42, "started_at": AT})
    )

    stored = attempts.get_latest(attempt.step_run_id)
    assert stored is not None
    assert (stored.start_sha, stored.pgid) == ("abc", 42)


def test_mark_finished_stores_the_other_half() -> None:
    attempt = an_attempt(new_id(), new_id(), 1)
    attempts = FakeAttemptRepository([attempt])

    attempts.mark_finished(
        attempt.model_copy(update={"end_sha": "def", "exit_code": 0, "status": "done"})
    )

    stored = attempts.get_latest(attempt.step_run_id)
    assert stored is not None
    assert (stored.end_sha, stored.exit_code, stored.status) == ("def", 0, "done")


def test_update_replaces_the_stored_attempt() -> None:
    attempt = an_attempt(new_id(), new_id(), 1)
    attempts = FakeAttemptRepository([attempt])

    attempts.update(attempt.model_copy(update={"cost_usd": Decimal("0.010000")}))

    stored = attempts.get_latest(attempt.step_run_id)
    assert stored is not None
    assert stored.cost_usd == Decimal("0.010000")


@pytest.mark.parametrize("method", ["mark_started", "mark_finished", "update"])
def test_writing_an_attempt_that_was_never_stored_is_refused(method: str) -> None:
    attempts = FakeAttemptRepository()

    with pytest.raises(ValueError, match="no attempt with id"):
        getattr(attempts, method)(an_attempt(new_id(), new_id(), 1))


def test_the_attempt_fake_records_the_two_halves_separately() -> None:
    attempt = an_attempt(new_id(), new_id(), 1)
    attempts = FakeAttemptRepository()

    attempts.add(attempt)
    attempts.mark_started(attempt)
    attempts.mark_finished(attempt)

    assert attempts.calls == [
        ("add", attempt.id),
        ("mark_started", attempt.id),
        ("mark_finished", attempt.id),
    ]


# ── GateRecordRepository ─────────────────────────────────────────────────────


def test_gate_records_are_listed_oldest_first() -> None:
    run_id = new_id()
    first = a_record(run_id, AT)
    second = a_record(run_id, AT + timedelta(seconds=1), event="blocked")
    records = FakeGateRecordRepository([second, first])

    assert records.list_for_run(run_id) == [first, second]


def test_two_records_at_the_same_instant_are_ordered_by_id() -> None:
    """UUIDv7 sorts by creation, so the id is the tiebreak the adapter's ORDER BY uses."""
    run_id = new_id()
    first = a_record(run_id, AT)
    second = a_record(run_id, AT)
    records = FakeGateRecordRepository([second, first])

    listed = records.list_for_run(run_id)

    assert listed == sorted([first, second], key=lambda record: record.id)


def test_gate_records_are_scoped_to_one_run() -> None:
    records = FakeGateRecordRepository([a_record(new_id(), AT)])

    assert records.list_for_run(new_id()) == []


def test_adding_the_same_gate_record_twice_is_refused() -> None:
    record = a_record(new_id(), AT)
    records = FakeGateRecordRepository([record])

    with pytest.raises(ValueError, match="already stored"):
        records.add(record)


def test_the_gate_record_fake_records_its_calls() -> None:
    run_id = new_id()
    record = a_record(run_id, AT)
    records = FakeGateRecordRepository()

    records.add(record)
    records.list_for_run(run_id)

    assert records.calls == [("add", record.id), ("list_for_run", run_id)]
