"""`apply_step_result` dependency resolution (story 5-4, AD-8).

When a Run reaches `done` via `apply_step_result`:
  - saved dependents are enqueued after the commit (engine.enqueue called, engine_ref written,
    after_run_id cleared).
  - the predecessor commits before enqueue (committed_when_called=True).

When a Run reaches `failed`:
  - saved dependents are parked `needs_you / dependency` in the same UoW.

`engine` must be wired into `WriterPorts` for enqueue to fire; when it is None, done-deps are
discovered but silently skipped.
"""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world, build_run
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.runs import FakeRunRepository

DONE = StepResult(status="done", gate="deterministic", output_ref="/work/logs/1.log")
FAILED = StepResult(status="error", gate="deterministic", output_ref="/work/logs/1.log")


def _world_with_engine_and_dependent(*, with_engine: bool = True):
    """A running predecessor (last step running) with a saved dependent, and an engine."""
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    predecessor = world.stored_run()
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})

    clock = world.clock
    uow = world.ports.uow
    engine = FakeWorkflowEngine(clock=clock, uow=uow)

    ports = WriterPorts(
        runs=FakeRunRepository([predecessor, dependent]),
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        records=world.ports.records,
        uow=uow,
        clock=clock,
        engine=engine if with_engine else None,
    )
    return predecessor, dependent, ports, engine


def _world_with_engine_and_dependent_failing():
    """A running predecessor (first step running → error causes fail) with a saved dependent.

    Uses `with_resolved={"plan": {"on_fail": "fail"}}` so that an `error` result on the
    first step fails the entire Run rather than escalating (the default escalate path does
    not fail the run — it leaves status unchanged until the executor returns a Park).
    """
    world = a_world("running", PAIR_PLAN, {"plan": "running"}, {"plan": {"on_fail": "fail"}})
    predecessor = world.stored_run()
    dependent = build_run(status="queued", after_run_id=predecessor.id, engine_ref={})

    clock = world.clock
    uow = world.ports.uow
    engine = FakeWorkflowEngine(clock=clock, uow=uow)

    ports = WriterPorts(
        runs=FakeRunRepository([predecessor, dependent]),
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        records=world.ports.records,
        uow=uow,
        clock=clock,
        engine=engine,
    )
    return predecessor, dependent, ports, engine


# ── done predecessor enqueues saved dependent ─────────────────────────────────


def test_done_predecessor_enqueues_saved_dependent() -> None:
    """When the last step completes and the Run becomes done, the saved dependent is enqueued."""
    predecessor, _dependent, ports, engine = _world_with_engine_and_dependent()

    apply_step_result(ports, predecessor.id, 2, DONE)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert len(enqueue_calls) == 1


def test_done_predecessor_clears_after_run_id_on_dependent() -> None:
    """After enqueue, after_run_id is cleared (startup sweep must not re-enqueue)."""
    predecessor, dependent, ports, _engine = _world_with_engine_and_dependent()

    apply_step_result(ports, predecessor.id, 2, DONE)

    stored_dep = ports.runs.get(dependent.id)
    assert stored_dep is not None
    assert stored_dep.after_run_id is None


def test_done_predecessor_sets_engine_ref_on_dependent() -> None:
    """After enqueue, the dependent has a non-empty engine_ref."""
    predecessor, dependent, ports, _engine = _world_with_engine_and_dependent()

    apply_step_result(ports, predecessor.id, 2, DONE)

    stored_dep = ports.runs.get(dependent.id)
    assert stored_dep is not None
    assert stored_dep.engine_ref  # truthy — non-empty dict


def test_done_predecessor_commits_before_enqueue() -> None:
    """The predecessor's terminal status must be committed before engine.enqueue is called."""
    predecessor, _dependent, ports, engine = _world_with_engine_and_dependent()

    apply_step_result(ports, predecessor.id, 2, DONE)

    # The first enqueue call must have seen the UoW already committed.
    enqueue_indices = [i for i, (name, _) in enumerate(engine.calls) if name == "enqueue"]
    assert enqueue_indices, "engine.enqueue was not called"
    first_idx = enqueue_indices[0]
    assert engine.committed_when_called[first_idx] is True


def test_done_predecessor_without_engine_does_not_raise() -> None:
    """With engine=None in WriterPorts, done-deps are discovered but not enqueued."""
    predecessor, dependent, ports, _engine = _world_with_engine_and_dependent(with_engine=False)

    # Should not raise — engine is optional.
    apply_step_result(ports, predecessor.id, 2, DONE)

    # Predecessor is done.
    stored = ports.runs.get(predecessor.id)
    assert stored is not None
    assert stored.status == "done"
    # Dependent is not touched (no engine).
    stored_dep = ports.runs.get(dependent.id)
    assert stored_dep is not None
    assert stored_dep.engine_ref == {}  # still empty
    assert stored_dep.after_run_id == predecessor.id  # still set


# ── failed predecessor parks saved dependent ─────────────────────────────────


def test_failed_predecessor_parks_dependent_in_same_unit_of_work() -> None:
    """When the last step fails the Run, saved dependents are parked as dependency."""
    predecessor, dependent, ports, _engine = _world_with_engine_and_dependent_failing()

    apply_step_result(ports, predecessor.id, 1, FAILED)

    stored_dep = ports.runs.get(dependent.id)
    assert stored_dep is not None
    assert stored_dep.status == "needs_you"
    assert stored_dep.park_kind == "dependency"
    assert stored_dep.park_path is None


def test_failed_predecessor_does_not_enqueue_dependent() -> None:
    """A failed predecessor must not enqueue its dependent."""
    predecessor, _dependent, ports, engine = _world_with_engine_and_dependent_failing()

    apply_step_result(ports, predecessor.id, 1, FAILED)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert enqueue_calls == []


# ── no dependents — baseline regression ──────────────────────────────────────


def test_done_run_without_dependents_needs_no_enqueue() -> None:
    """A Run that completes with no saved dependents does not call enqueue at all."""
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    predecessor = world.stored_run()
    clock = world.clock
    uow = world.ports.uow
    engine = FakeWorkflowEngine(clock=clock, uow=uow)
    ports = WriterPorts(
        runs=FakeRunRepository([predecessor]),
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        records=world.ports.records,
        uow=uow,
        clock=clock,
        engine=engine,
    )

    apply_step_result(ports, predecessor.id, 2, DONE)

    enqueue_calls = [name for name, _ in engine.calls if name == "enqueue"]
    assert enqueue_calls == []
