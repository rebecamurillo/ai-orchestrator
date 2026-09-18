"""`apply_step_result` end-to-end with dependency-waiting dependents (story 5-4).

AC coverage (P2 and P3 from patch review):
- When apply_step_result drives a predecessor to `failed`, dependent Runs with
  after_run_id=predecessor.id are parked with park_kind="dependency" in the same UoW.
- When apply_step_result drives a predecessor to `done`, dependent Runs are enqueued
  (engine.enqueue called, engine_ref written).
- These cover the park_dependents / enqueue_dependents call-sites in apply_step_result.py
  that would not be caught by deleting them if only the helpers are unit-tested.
"""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.entities.run import Run
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, PAIR_PLAN, a_world, build_run


def a_dependent(predecessor_id: object) -> Run:
    return build_run("queued", after_run_id=predecessor_id)


# ── failed predecessor parks dependents ───────────────────────────────────────────────────


def test_apply_step_result_failed_parks_dependency_waiting_run() -> None:
    """on_fail=fail: predecessor ends failed → dependent status becomes needs_you."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {"baseline": "running"},
        with_resolved={"baseline": {"on_fail": "fail"}},
    )
    dependent = a_dependent(world.run.id)
    world.ports.runs.add(dependent)

    apply_step_result(
        world.ports,
        world.run.id,
        3,
        StepResult(status="error", gate="deterministic", reason="baseline exit 1"),
    )

    stored = world.ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


def test_apply_step_result_failed_writes_gate_record_for_dependent() -> None:
    world = a_world(
        "running",
        EPIC_PLAN,
        {"baseline": "running"},
        with_resolved={"baseline": {"on_fail": "fail"}},
    )
    dependent = a_dependent(world.run.id)
    world.ports.runs.add(dependent)

    apply_step_result(
        world.ports,
        world.run.id,
        3,
        StepResult(status="error", gate="deterministic", reason="baseline exit 1"),
    )

    records = world.ports.records.list_for_run(dependent.id)
    assert any(r.event == "dependency" and r.actor == "machine" for r in records)


# ── done predecessor enqueues dependents ──────────────────────────────────────────────────


def test_apply_step_result_done_enqueues_dependency_waiting_run() -> None:
    """Last row done: predecessor ends done → dependent is enqueued via engine."""
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    dependent = a_dependent(world.run.id)
    world.ports.runs.add(dependent)
    # Wire the engine into WriterPorts so enqueue_dependents is not a no-op.
    ports_with_engine = replace(world.ports, engine=world.engine)

    apply_step_result(
        ports_with_engine,
        world.run.id,
        2,
        StepResult(status="done", gate="deterministic"),
    )

    stored = world.ports.runs.get(dependent.id)
    assert stored is not None
    assert stored.engine_ref != {}
    assert any(name == "enqueue" for name, _ in world.engine.calls)
