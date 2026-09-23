"""Cancelling a Run parks its dependency-waiting dependents in the same UoW (story 5-4).

AC coverage:
- When operator cancels a Run with waiting dependents, each is parked with
  park_kind="dependency" in the same unit of work as the cancel.
- Dependents already enqueued (engine_ref non-empty) are not affected.
- Gate records are written for parked dependents.
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.engine import FakeWorkflowEngine

BUDGET = Decimal("10.00")
CANCEL = Signal(kind="cancel", payload={})


def a_queued_run_waiting_for(predecessor_id: object, **over: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "queued",
        "budget_usd": BUDGET,
        "created_at": EPOCH,
        # Revised for fan-in after_run_ids (multi-repo initiative S1, spine AD-12/AD-13
        # amendment, 2026-09-23): the 1:1 pointer became a list.
        "after_run_ids": (predecessor_id,),
        "engine_ref": {},
    }
    fields.update(over)
    return Run(**fields)  # type: ignore[arg-type]


def cancel_world_with_dependent(
    run_status: str = "running",
) -> tuple[SignalPorts, Run, Run, FakeWorkflowEngine]:
    """A running (or queued) Run, plus a dependent waiting for it."""
    world = a_world(run_status, PAIR_PLAN, {"plan": run_status} if run_status != "queued" else None)
    dependent = a_queued_run_waiting_for(world.run.id)
    world.ports.runs.add(dependent)
    ports = SignalPorts(writers=world.ports, engine=world.engine)
    return ports, world.run, dependent, world.engine


# ── cancel parks dependents ────────────────────────────────────────────────────────────────


def test_cancel_parks_dependency_waiting_run() -> None:
    ports, predecessor, dependent, _ = cancel_world_with_dependent("running")

    signal_run(ports, predecessor.id, CANCEL)

    stored = ports.writers.runs.get(dependent.id)
    assert stored is not None
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


def test_cancel_writes_gate_record_for_dependent() -> None:
    ports, predecessor, dependent, _ = cancel_world_with_dependent("running")

    signal_run(ports, predecessor.id, CANCEL)

    records = ports.writers.records.list_for_run(dependent.id)
    assert any(r.event == "dependency" and r.actor == "machine" for r in records)


def test_cancel_does_not_affect_already_enqueued_dependent() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    already_running = a_queued_run_waiting_for(world.run.id, engine_ref={"ref": 1})
    world.ports.runs.add(already_running)
    ports = SignalPorts(writers=world.ports, engine=world.engine)

    signal_run(ports, world.run.id, CANCEL)

    stored = ports.writers.runs.get(already_running.id)
    assert stored is not None
    # engine_ref is non-empty → list_dependents excluded it
    assert stored.status == "queued"


def test_cancel_on_run_with_no_dependents_works_normally() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    ports = SignalPorts(writers=world.ports, engine=world.engine)

    outcome = signal_run(ports, world.run.id, CANCEL)

    assert outcome.run.status == "cancelled"
