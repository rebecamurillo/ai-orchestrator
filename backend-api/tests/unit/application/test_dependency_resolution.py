"""`park_dependents` and `enqueue_dependents` — dependency resolution helpers (story 5-4).

AC coverage:
- When predecessor reaches `failed`, dependents with after_run_id set are parked with
  park_kind="dependency" in the same unit of work.
- When predecessor reaches `done`, dependents are enqueued via engine (two-phase commit).
- `enqueue_dependents` is a no-op when engine is None.
- `park_dependents` writes no records when no dependents exist.
- Dependency park writes gate record with event="dependency" and actor="machine".
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.writers import (
    WriterPorts,
    enqueue_dependents,
    park_dependents,
)
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


# ── park_dependents ───────────────────────────────────────────────────────────────────────


def testpark_dependents_sets_needs_you_with_dependency_kind() -> None:
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
    assert stored.park_path is None


def testpark_dependents_writes_gate_record_with_dependency_event() -> None:
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    records = ports.records.list_for_run(dependent.id)
    assert len(records) == 1
    assert records[0].event == "dependency"
    assert records[0].actor == "machine"
    assert records[0].path is None


def testpark_dependents_includes_predecessor_id_and_status_in_reason() -> None:
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert str(predecessor.id) in stored.park_reason
    assert "failed" in stored.park_reason


def testpark_dependents_does_nothing_when_no_dependents() -> None:
    predecessor = a_run("failed")
    ports = make_ports([predecessor])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    # no records written, no update calls for the predecessor
    records = ports.records.list_for_run(predecessor.id)
    assert records == []


def testpark_dependents_skips_already_enqueued_dependents() -> None:
    """list_by_after_run_id only returns engine_ref=={} runs."""
    predecessor = a_run("cancelled")
    # already enqueued — should NOT be in list_by_after_run_id
    already_running = a_run("queued", after_run_id=predecessor.id, engine_ref={"ref": 1})
    ports = make_ports([predecessor, already_running])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    stored = ports.runs.get(already_running.id)
    assert stored is not None
    assert stored.status == "queued"  # unchanged


# ── enqueue_dependents ────────────────────────────────────────────────────────────────────


def testenqueue_dependents_enqueues_waiting_run_after_predecessor_done() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    assert any(name == "enqueue" for name, _ in engine.calls)


def testenqueue_dependents_commits_engine_ref_on_dependent() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref != {}


def testenqueue_dependents_is_noop_when_engine_is_none() -> None:
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)
    ports = make_ports([predecessor, dependent], engine=None)

    # no exception, no side effects
    enqueue_dependents(ports, None, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref == {}


def testenqueue_dependents_is_idempotent_for_already_enqueued() -> None:
    """list_by_after_run_id returns engine_ref=={} only; already-enqueued runs are invisible."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    # already enqueued
    already = a_run("queued", after_run_id=predecessor.id, engine_ref={"ref": 99})
    ports = make_ports([predecessor, already], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    # engine was NOT called for this already-enqueued run
    enqueue_calls = [args for name, args in engine.calls if name == "enqueue"]
    assert not any(run_id == already.id for run_id, _ in enqueue_calls)


def testenqueue_dependents_handles_run_deleted_between_list_and_get() -> None:
    """If the dependent is deleted after list_by_after_run_id but before get(), no crash."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_id=predecessor.id)

    class _DeleteOnGet(FakeRunRepository):
        def get(self, run_id: object) -> object:  # type: ignore[override]
            return None  # simulate deletion between list and get

    uow = FakeUnitOfWork()
    ports = WriterPorts(
        runs=_DeleteOnGet([predecessor, dependent]),
        steps=FakeStepRunRepository(),
        attempts=FakeAttemptRepository(),
        records=FakeGateRecordRepository(),
        uow=uow,
        clock=FakeClock(),
        engine=engine,
    )

    # Must not raise; engine.enqueue is still called, but set_run is skipped.
    enqueue_dependents(ports, engine, predecessor)

    assert any(name == "enqueue" for name, _ in engine.calls)
