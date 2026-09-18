"""`list_queue` (SPEC CAP-11, FR-13, FR-25, AD-12): the queue joined with `run`/`step_run`.

Every scenario is one of the brief's own ACs, plus the pure `_next_step_label` cases
`application/use_cases/project_runs.py::test_project_runs.py` already proves for its own
twin function — the same four branches, read here against the queue's own fixtures.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from orchestrator.application.use_cases.queue import (
    REASON_BRANCH_HELD,
    REASON_GLOBAL_CONCURRENCY,
    REASON_RUNNING,
    REASON_WAITING_ANSWER,
    QueuePorts,
    list_queue,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.engine import QueueEntry
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
REPOSITORY_A = new_id()
REPOSITORY_B = new_id()
REPOSITORY_C = new_id()
PROJECT = new_id()


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT,
        "repository_id": REPOSITORY_A,
        "template_name": "epic",
        "template_version": 1,
        "status": "running",
        "budget_usd": 0,
        "inputs": {"branch": "feat/x"},
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(run_id: object, seq: int, path: str, label: str, status: str) -> StepRun:
    return StepRun(  # type: ignore[call-arg]
        id=new_id(),
        run_id=run_id,
        seq=seq,
        path=path,
        label=label,
        kind="shell",
        gate="deterministic",
        status=status,
    )


def a_ports(
    engine: FakeWorkflowEngine, runs: FakeRunRepository, *, max_active_runs: int = 2
) -> QueuePorts:
    return QueuePorts(
        engine=engine,
        runs=runs,
        steps=FakeStepRunRepository(),
        clock=FakeClock(NOW),
        max_active_runs=max_active_runs,
    )


def entry(run_id: object, state: str, position: int | None, enqueued_at: datetime) -> QueueEntry:
    return QueueEntry(run_id=run_id, engine_state=state, position=position, enqueued_at=enqueued_at)  # type: ignore[arg-type]


# ── AC1: repository lock, running, and a parked Run on another repository ───────────────────


def test_running_queued_and_parked_runs_read_the_fixed_reasons() -> None:
    # operator revision 2026-09-15: partition by (repository, branch); both runs need
    # partition_branch set to the same value for REASON_BRANCH_HELD to be reported.
    running = a_run(repository_id=REPOSITORY_A, status="running", partition_branch="feat/x")
    queued = a_run(repository_id=REPOSITORY_A, status="queued", partition_branch="feat/x")
    parked = a_run(
        repository_id=REPOSITORY_B,
        status="needs_you",
        park_kind="checkpoint",
        park_path="review",
    )
    runs = FakeRunRepository([running, queued, parked])
    engine = FakeWorkflowEngine()
    engine.queue[running.id] = entry(running.id, "pending", None, NOW)
    engine.queue[queued.id] = entry(queued.id, "enqueued", 1, NOW)
    engine.queue[parked.id] = entry(parked.id, "pending", None, NOW)

    view = list_queue(a_ports(engine, runs))

    by_id = {row.run.id: row for row in view.items}
    assert by_id[running.id].reason == REASON_RUNNING
    assert by_id[running.id].position is None
    assert by_id[queued.id].position == 1
    # operator revision 2026-09-15: partition by (repository, branch)
    assert by_id[queued.id].reason == REASON_BRANCH_HELD.format(run="epic · feat/x")
    assert by_id[parked.id].reason == REASON_WAITING_ANSWER
    assert by_id[parked.id].position is None


# ── AC2: global concurrency ───────────────────────────────────────────────────────────────


def test_an_enqueued_run_with_a_free_repository_reads_global_concurrency() -> None:
    """Two active Runs on two different Repositories, a third enqueued on a third: the
    waiting Run's own Repository holds nothing, so the reason names every active label."""
    active_one = a_run(
        repository_id=REPOSITORY_A,
        status="running",
        inputs={"branch": "feat/a"},
        created_at=NOW - timedelta(seconds=10),
    )
    active_two = a_run(
        repository_id=REPOSITORY_B, status="running", inputs={"branch": "feat/b"}, created_at=NOW
    )
    waiting = a_run(repository_id=REPOSITORY_C, status="queued")
    runs = FakeRunRepository([active_one, active_two, waiting])
    engine = FakeWorkflowEngine()
    engine.queue[active_one.id] = entry(active_one.id, "pending", None, NOW)
    engine.queue[active_two.id] = entry(active_two.id, "pending", None, NOW)
    engine.queue[waiting.id] = entry(waiting.id, "enqueued", 1, NOW)

    view = list_queue(a_ports(engine, runs, max_active_runs=2))

    row = next(r for r in view.items if r.run.id == waiting.id)
    # `FakeRunRepository.list_by_status` reads newest first: `active_two` (created later)
    # before `active_one`.
    # operator revision 2026-09-15: partition by (repository, branch)
    assert row.reason == REASON_GLOBAL_CONCURRENCY.format(runs="epic · feat/b, epic · feat/a")
    assert row.position == 1


# ── ordering (AD-12): active first, then queued by position, parked last ───────────────────


def test_ordering_is_active_then_queued_by_position_then_parked() -> None:
    running = a_run(repository_id=REPOSITORY_A, status="running")
    second = a_run(repository_id=REPOSITORY_A, status="queued")
    parked = a_run(
        repository_id=REPOSITORY_B, status="needs_you", park_kind="blocked", park_path="build"
    )
    runs = FakeRunRepository([running, second, parked])
    engine = FakeWorkflowEngine()
    engine.queue[parked.id] = entry(parked.id, "pending", None, NOW)
    engine.queue[second.id] = entry(second.id, "enqueued", 1, NOW)
    engine.queue[running.id] = entry(running.id, "pending", None, NOW)

    view = list_queue(a_ports(engine, runs))

    assert [row.run.id for row in view.items] == [running.id, second.id, parked.id]


# ── the join: a Run the engine still names but storage no longer holds ──────────────────────


def test_an_entry_for_a_run_no_longer_stored_is_dropped() -> None:
    engine = FakeWorkflowEngine()
    engine.queue[new_id()] = entry(new_id(), "enqueued", 1, NOW)

    view = list_queue(a_ports(engine, FakeRunRepository()))

    assert view.items == []


def test_max_active_runs_is_carried_through() -> None:
    ceiling = 5
    view = list_queue(a_ports(FakeWorkflowEngine(), FakeRunRepository(), max_active_runs=ceiling))

    assert view.max_active_runs == ceiling


def test_waiting_seconds_is_measured_from_the_clock() -> None:
    elapsed = timedelta(seconds=90)
    run = a_run(status="queued")
    runs = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "enqueued", 1, NOW - elapsed)

    view = list_queue(a_ports(engine, runs))

    assert view.items[0].waiting_seconds == elapsed.total_seconds()
    assert view.items[0].waiting_since == NOW - elapsed


# ── next_step_label ──────────────────────────────────────────────────────────────────────


def a_ports_with_steps(
    engine: FakeWorkflowEngine, runs: FakeRunRepository, steps: list[StepRun]
) -> QueuePorts:
    return QueuePorts(
        engine=engine,
        runs=runs,
        steps=FakeStepRunRepository(steps),
        clock=FakeClock(NOW),
        max_active_runs=2,
    )


def test_next_step_label_is_empty_with_no_rows() -> None:
    run = a_run(status="running")
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "pending", None, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), []))

    assert view.items[0].next_step_label == ""


def test_next_step_label_prefers_the_parked_row() -> None:
    run = a_run(status="needs_you", park_kind="blocked", park_path="install")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "blocked"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "pending", None, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "install"


def test_next_step_label_falls_back_when_the_parked_path_names_no_row() -> None:
    """Defensive: a stored `park_path` should always name a real row, but the lookup does
    not assume it — falling through to the next check is the honest answer either way."""
    run = a_run(status="needs_you", park_kind="blocked", park_path="gone")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "running"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "pending", None, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "install"


def test_next_step_label_falls_back_to_the_running_row() -> None:
    run = a_run(status="running")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "running"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "pending", None, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "install"


def test_next_step_label_falls_back_to_the_queued_row() -> None:
    run = a_run(status="queued")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "queued"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "enqueued", 1, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "install"


def test_next_step_label_falls_back_to_the_next_planned_row_before_anything_started() -> None:
    run = a_run(status="queued")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "planned"),
        a_row(run.id, 2, "install", "install", "planned"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "enqueued", 1, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "checkout"


def test_next_step_label_is_the_last_row_touched_once_the_run_is_terminal() -> None:
    run = a_run(status="done")
    rows = [
        a_row(run.id, 1, "checkout", "checkout", "done"),
        a_row(run.id, 2, "install", "install", "done"),
    ]
    engine = FakeWorkflowEngine()
    engine.queue[run.id] = entry(run.id, "pending", None, NOW)

    view = list_queue(a_ports_with_steps(engine, FakeRunRepository([run]), rows))

    assert view.items[0].next_step_label == "install"
