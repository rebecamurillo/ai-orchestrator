"""`resolve_dependent`, `park_dependents` and `enqueue_dependents` — fan-in resolution.

Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13 amendment,
2026-09-23): the 1:1 `after_run_id` pointer became the list `after_run_ids`, and the rule
AD-12 states is a read of the dependent's whole predecessor list — ALL `done` → enqueue,
ANY `failed | cancelled` → park naming that predecessor, otherwise still waiting.

AC coverage:
- ALL predecessors `done` → two-phase enqueue (one predecessor, and two).
- ANY predecessor `failed | cancelled` → park `needs_you` / `dependency`, reason naming
  that predecessor (one predecessor, and one of two).
- Neither → no-op: nothing written, the dependent stays `queued`.
- A predecessor id that no longer resolves to a Run → park, reason naming it missing
  (S1 design choice: a dangling edge is surfaced to the Operator, never silently waited on).
- `enqueue_dependents` is a no-op when engine is None.
- `park_dependents` writes no records when no dependents exist.
- Dependency park writes gate record with event="dependency" and actor="machine".
- `list_dependents` returns only `engine_ref == {}` runs, so an enqueued dependent is
  invisible to both helpers.
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.writers import (
    DEPENDENCY_MISSING_REASON,
    DEPENDENCY_PARK_REASON,
    WriterPorts,
    enqueue_dependents,
    park_dependents,
    resolve_dependent,
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
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
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
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
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
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.park_reason == DEPENDENCY_PARK_REASON.format(
        run_id=predecessor.id, status="failed"
    )


def testpark_dependents_retains_the_whole_predecessor_list() -> None:
    """AD-12 (2026-09-23): the retained edges are the initiative's durable DAG record."""
    predecessor = a_run("failed")
    other = a_run("running")
    dependent = a_run("queued", after_run_ids=(predecessor.id, other.id))
    ports = make_ports([predecessor, other, dependent])

    with ports.uow:
        park_dependents(ports, predecessor)
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.after_run_ids == (predecessor.id, other.id)


def testpark_dependents_names_the_failed_predecessor_of_a_fan_in() -> None:
    """Two predecessors, one done and one cancelled: the reason names the cancelled one."""
    done = a_run("done")
    cancelled = a_run("cancelled")
    dependent = a_run("queued", after_run_ids=(done.id, cancelled.id))
    ports = make_ports([done, cancelled, dependent])

    with ports.uow:
        park_dependents(ports, cancelled)
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.park_reason == DEPENDENCY_PARK_REASON.format(
        run_id=cancelled.id, status="cancelled"
    )
    assert str(done.id) not in (stored.park_reason or "")


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
    """list_dependents only returns engine_ref=={} runs."""
    predecessor = a_run("cancelled")
    # already enqueued — should NOT be in list_dependents
    already_running = a_run("queued", after_run_ids=(predecessor.id,), engine_ref={"ref": 1})
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
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    assert any(name == "enqueue" for name, _ in engine.calls)


def testenqueue_dependents_commits_engine_ref_on_dependent() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref != {}


def testenqueue_dependents_enqueues_only_when_every_predecessor_is_done() -> None:
    """Fan-in: two predecessors both `done` → the dependent is enqueued once."""
    engine = FakeWorkflowEngine()
    first = a_run("done")
    second = a_run("done")
    dependent = a_run("queued", after_run_ids=(first.id, second.id))
    ports = make_ports([first, second, dependent], engine=engine)

    enqueue_dependents(ports, engine, second)

    enqueued = [run_id for name, (run_id, _key) in engine.calls if name == "enqueue"]
    assert enqueued == [dependent.id]


def testenqueue_dependents_waits_while_one_predecessor_is_still_running() -> None:
    """Fan-in: one `done`, one `running` → nothing is enqueued, nothing is written."""
    engine = FakeWorkflowEngine()
    done = a_run("done")
    running = a_run("running")
    dependent = a_run("queued", after_run_ids=(done.id, running.id))
    ports = make_ports([done, running, dependent], engine=engine)

    enqueue_dependents(ports, engine, done)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.engine_ref == {}
    assert engine.calls == []
    assert ports.records.list_for_run(dependent.id) == []


def testenqueue_dependents_retains_the_predecessor_list_after_enqueue() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.after_run_ids == (predecessor.id,)


def testenqueue_dependents_is_noop_when_engine_is_none() -> None:
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=None)

    # no exception, no side effects
    enqueue_dependents(ports, None, predecessor)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref == {}


def testenqueue_dependents_is_idempotent_for_already_enqueued() -> None:
    """list_dependents returns engine_ref=={} only; already-enqueued runs are invisible."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    # already enqueued
    already = a_run("queued", after_run_ids=(predecessor.id,), engine_ref={"ref": 99})
    ports = make_ports([predecessor, already], engine=engine)

    enqueue_dependents(ports, engine, predecessor)

    # engine was NOT called for this already-enqueued run
    enqueue_calls = [args for name, args in engine.calls if name == "enqueue"]
    assert not any(run_id == already.id for run_id, _ in enqueue_calls)


def testenqueue_dependents_handles_run_deleted_between_list_and_get() -> None:
    """If the dependent is deleted after list_dependents but before get(), no crash."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))

    class _PredecessorOnlyOnGet(FakeRunRepository):
        """`get` answers for the predecessor and nothing else: the dependent vanished."""

        def get(self, run_id: object) -> object:  # type: ignore[override]
            return super().get(run_id) if run_id == predecessor.id else None  # type: ignore[arg-type]

    uow = FakeUnitOfWork()
    ports = WriterPorts(
        runs=_PredecessorOnlyOnGet([predecessor, dependent]),
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


# ── resolve_dependent: the rule itself ────────────────────────────────────────────────────


def test_resolve_dependent_parks_when_a_predecessor_id_is_missing() -> None:
    """S1 design choice: a dangling edge parks for the Operator, it never waits forever.

    `after_run_ids` carries no foreign key, so an id that no longer resolves to a Run is a
    state the resolver must decide about. Parking surfaces it (`continue` starts the Run
    anyway, `cancel` ends it); skipping would strand the Run invisibly.
    """
    missing_id = new_id()
    dependent = a_run("queued", after_run_ids=(missing_id,))
    ports = make_ports([dependent])

    resolve_dependent(ports, None, dependent)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
    assert stored.park_reason == DEPENDENCY_MISSING_REASON.format(run_id=missing_id)


def test_resolve_dependent_names_the_first_blocking_predecessor_in_declared_order() -> None:
    """Two blocking predecessors: the earlier one in `after_run_ids` is the one named."""
    failed = a_run("failed")
    missing_id = new_id()
    dependent = a_run("queued", after_run_ids=(failed.id, missing_id))
    ports = make_ports([failed, dependent])

    resolve_dependent(ports, None, dependent)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.park_reason == DEPENDENCY_PARK_REASON.format(run_id=failed.id, status="failed")


def test_resolve_dependent_writes_nothing_when_every_predecessor_is_done_but_engine_is_none() -> (
    None
):
    """The degraded path: no engine wired, so the Run stays exactly where it was.

    `park_dependents` reaches `resolve_dependent` this way on purpose — it passes no engine
    because a failed or cancelled predecessor can never enqueue anyone — and so does every
    `WriterPorts` built before story 5-4.
    """
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=None)

    resolve_dependent(ports, None, dependent)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.engine_ref == {}
    assert ports.records.list_for_run(dependent.id) == []


def test_resolve_dependent_is_a_noop_for_a_run_with_no_predecessors() -> None:
    """A saved Run with an empty list is nobody's dependent — it waits for the operator."""
    engine = FakeWorkflowEngine()
    dependent = a_run("queued")
    ports = make_ports([dependent], engine=engine)

    resolve_dependent(ports, engine, dependent)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.engine_ref == {}
    assert engine.calls == []


def test_resolve_dependent_writes_the_park_in_the_callers_uow_when_asked() -> None:
    """`own_uow=False` is the AD-8 path: the park lands in the predecessor's own UoW."""
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    with ports.uow:
        resolve_dependent(ports, None, dependent, own_uow=False)
        # still inside the caller's transaction: nothing has been committed by the resolver
        assert ports.uow.calls == ["enter"]  # type: ignore[attr-defined]
        ports.uow.commit()

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"


def test_resolve_dependent_opens_its_own_uow_for_a_park_by_default() -> None:
    """The sweep and the post-commit enqueue path call it with no transaction open."""
    predecessor = a_run("cancelled")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    resolve_dependent(ports, None, dependent)

    assert ports.uow.calls == ["enter", "commit", "exit"]  # type: ignore[attr-defined]
    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
