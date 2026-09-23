"""`sweep_dependency_waiting` — startup crash-recovery sweep (story 5-4, AD-12).

Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13 amendment,
2026-09-23): the sweep no longer groups dependents by a single predecessor id — it walks
every `queued` Run with a non-empty `after_run_ids` and an empty `engine_ref` and applies
`resolve_dependent`, the same rule the two run-time writers apply.

AC coverage:
- Dependents whose predecessors are all `done` are enqueued via engine (one, and two).
- Dependents with any `failed` predecessor are parked with park_kind="dependency".
- Dependents with any `cancelled` predecessor are parked with park_kind="dependency".
- Dependents whose predecessors are not yet all terminal are skipped.
- Dependents whose predecessor is not found are parked (the S1 missing-predecessor rule).
- The sweep is idempotent: a second sweep changes nothing, for both the enqueue and the
  park path.
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
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    assert any(name == "enqueue" for name, _ in engine.calls)


def test_sweep_commits_engine_ref_when_predecessor_done() -> None:
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref != {}


def test_sweep_enqueues_a_fan_in_dependent_once_every_predecessor_is_done() -> None:
    engine = FakeWorkflowEngine()
    first = a_run("done")
    second = a_run("done")
    dependent = a_run("queued", after_run_ids=(first.id, second.id))
    ports = make_ports([first, second, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    enqueued = [run_id for name, (run_id, _key) in engine.calls if name == "enqueue"]
    assert enqueued == [dependent.id]


# ── predecessor failed: park ────────────────────────────────────────────────────────────────


def test_sweep_parks_when_predecessor_is_failed() -> None:
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


def test_sweep_parks_a_fan_in_dependent_naming_the_failed_predecessor() -> None:
    done = a_run("done")
    failed = a_run("failed")
    dependent = a_run("queued", after_run_ids=(done.id, failed.id))
    ports = make_ports([done, failed, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.park_kind == "dependency"
    assert str(failed.id) in (stored.park_reason or "")


# ── predecessor cancelled: park ─────────────────────────────────────────────────────────────


def test_sweep_parks_when_predecessor_is_cancelled() -> None:
    predecessor = a_run("cancelled")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


# ── skip non-terminal predecessors ────────────────────────────────────────────────────────


def test_sweep_skips_when_predecessor_is_running() -> None:
    predecessor = a_run("running")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"


def test_sweep_skips_when_predecessor_is_queued() -> None:
    predecessor = a_run("queued")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"


def test_sweep_skips_a_fan_in_dependent_while_one_predecessor_still_runs() -> None:
    engine = FakeWorkflowEngine()
    done = a_run("done")
    running = a_run("running")
    dependent = a_run("queued", after_run_ids=(done.id, running.id))
    ports = make_ports([done, running, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "queued"
    assert stored.engine_ref == {}
    assert engine.calls == []


def test_sweep_parks_when_predecessor_not_found() -> None:
    """S1 missing-predecessor rule: a dangling edge is surfaced, never silently waited on.

    Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13
    amendment, 2026-09-23). `after_run_ids` carries no foreign key, so an id whose Run is
    gone can no longer be repaired by the database; the Operator sees the park and answers
    it with `continue` (start anyway) or `cancel`.
    """
    missing_id = new_id()
    dependent = a_run("queued", after_run_ids=(missing_id,))
    ports = make_ports([dependent])

    sweep_dependency_waiting(ports, None)

    stored = ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"
    assert str(missing_id) in (stored.park_reason or "")


# ── no waiting runs ────────────────────────────────────────────────────────────────────────


def test_sweep_is_noop_when_no_waiting_runs() -> None:
    predecessor = a_run("done")
    ports = make_ports([predecessor])

    sweep_dependency_waiting(ports, None)

    # No exception, no side effects
    stored = ports.runs.get(predecessor.id)
    assert stored is not None
    assert stored.status == "done"


def test_sweep_ignores_a_saved_run_with_no_predecessors() -> None:
    """A saved Run waits for the Operator, not for a predecessor — the sweep leaves it."""
    engine = FakeWorkflowEngine()
    saved = a_run("queued")
    ports = make_ports([saved], engine=engine)

    sweep_dependency_waiting(ports, engine)

    stored = ports.runs.get(saved.id)
    assert stored is not None
    assert stored.status == "queued"
    assert engine.calls == []


# ── idempotency ────────────────────────────────────────────────────────────────────────────


def test_sweep_is_idempotent_for_already_enqueued_dependents() -> None:
    """list_dependents only returns engine_ref=={} runs."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    already = a_run("queued", after_run_ids=(predecessor.id,), engine_ref={"ref": 42})
    ports = make_ports([predecessor, already], engine=engine)

    sweep_dependency_waiting(ports, engine)

    # Engine was not called for this already-enqueued run
    enqueue_calls = [(name, args) for name, args in engine.calls if name == "enqueue"]
    assert not any(run_id == already.id for run_id, _ in enqueue_calls)


def test_a_second_sweep_enqueues_nothing_more() -> None:
    """Replay: the engine_ref the first sweep committed hides the Run from the second."""
    engine = FakeWorkflowEngine()
    predecessor = a_run("done")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent], engine=engine)

    sweep_dependency_waiting(ports, engine)
    first_pass = list(engine.calls)
    sweep_dependency_waiting(ports, engine)

    assert engine.calls == first_pass


def test_a_second_sweep_writes_no_second_dependency_park() -> None:
    """Replay: the park left the Run `needs_you`, which `list_dependents` no longer sees."""
    predecessor = a_run("failed")
    dependent = a_run("queued", after_run_ids=(predecessor.id,))
    ports = make_ports([predecessor, dependent])

    sweep_dependency_waiting(ports, None)
    sweep_dependency_waiting(ports, None)

    assert len(ports.records.list_for_run(dependent.id)) == 1
