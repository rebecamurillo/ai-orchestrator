"""`sweep_dependency_waiting` — startup crash-recovery sweep (story 5-4, AD-12).

AC coverage:
- Dependents whose predecessor is `done` are enqueued via engine.
- Dependents whose predecessor is `failed` are parked with park_kind="dependency".
- Dependents whose predecessor is `cancelled` are parked with park_kind="dependency".
- Dependents whose predecessor is not yet terminal are skipped.
- Dependents whose predecessor is not found are skipped.
- The sweep is idempotent: already-enqueued dependents (engine_ref non-empty) are invisible.
- No exception when there are no waiting runs.
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.dependency_sweep import sweep_dependency_waiting
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)

BUDGET = Decimal("10.00")


def a_run(status: str = "queued", **over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": status,
        "budget_usd": BUDGET,
        "created_at": EPOCH,
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def make_ports(
    runs: list[Run],
    engine: FakeWorkflowEngine | None = None,
) -> WriterPorts:
    uow = FakeUnitOfWork()
    return WriterPorts(
        runs=FakeRunRepository(runs),
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=uow,
        clock=FakeClock(),
        engine=engine,
    )


# ── predecessor done: enqueue ──────────────────────────────────────────────────────────────


def test_sweep_enqueues_when_predecessor_is_done() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    assert any(name == "enqueue" for name, _ in engine.calls)


def test_sweep_commits_engine_ref_when_predecessor_done() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref != {}


# ── predecessor failed: park ────────────────────────────────────────────────────────────────


def test_sweep_parks_when_predecessor_is_failed() -> None:
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


# ── predecessor cancelled: park ─────────────────────────────────────────────────────────────


def test_sweep_parks_when_predecessor_is_cancelled() -> None:
    predecessor = a_run("cancelled")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


# ── skip non-terminal predecessors ────────────────────────────────────────────────────────


def test_sweep_skips_when_predecessor_is_running() -> None:
    predecessor = a_run("running")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"


def test_sweep_skips_when_predecessor_is_queued() -> None:
    predecessor = a_run("queued")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"


def test_sweep_skips_when_predecessor_not_found() -> None:
    missing_id = new_id()
    dependent = a_run("queued", after_run_id=missing_id)
    ports = make_ports([dependent])

    # No exception
    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"


# ── no waiting runs ────────────────────────────────────────────────────────────────────────


def test_sweep_is_noop_when_no_waiting_runs() -> None:
    predecessor = a_run("done")
    ports = make_ports([predecessor])

    sweep_dependency_waiting(ports, None)

    # No exception, no side effects
    stored = ports.runs.get(predecessor.id)
    assert stored is not None
    assert stored.status == "done"


# ── idempotency ────────────────────────────────────────────────────────────────────────────


def test_sweep_is_idempotent_for_already_enqueued_dependents() -> None:
    """list_by_after_run_id only returns engine_ref=={} runs."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    already = a_run("queued", after_run_id=predecessor.id, engine_ref={"ref": 42})
    ports = make_ports([predecessor, already], engine=engine)

    sweep_dependency_waiting(ports, engine)

    # Engine was not called for this already-enqueued run
    enqueue_calls = [(name, args) for name, args in engine.calls if name == "enqueue"]
    assert not any(run_id == already.id for run_id, _ in enqueue_calls)
