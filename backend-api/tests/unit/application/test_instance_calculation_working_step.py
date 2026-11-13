"""A running metrics calculation is a working step (epic 2 story 5: AC8 hold/activity half)."""

from __future__ import annotations

import pytest

from orchestrator.application.preflight.checks import run_label
from orchestrator.application.use_cases.instance_activity import (
    ActivityPorts,
    WorkingStep,
    read_activity,
    working_steps,
)
from orchestrator.application.use_cases.instance_hold import HoldPorts, HoldRefused, place_hold
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.domain.entities.metric_results import MetricCalculation
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import World, a_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository
from tests.unit.fakes.metric_results import FakeMetricCalculationRepository


def with_calculation(state: str) -> tuple[World, FakeMetricCalculationRepository]:
    world = a_world("done")
    calculations = FakeMetricCalculationRepository()
    calculations.add(
        MetricCalculation(
            id=new_id(),
            run_id=world.run.id,
            target_n=3,
            state=state,  # type: ignore[arg-type]
            entry_point=("manual",),
            queued_at=world.clock.now(),
            started_at=world.clock.now() if state == "running" else None,
        )
    )
    return world, calculations


def test_a_running_calculation_is_listed_with_its_kind_and_path() -> None:
    world, calculations = with_calculation("running")

    found = working_steps(world.ports.runs, world.ports.steps, world.ports.attempts, calculations)

    assert found == [
        WorkingStep(
            run_id=world.run.id,
            run_label=run_label(world.run),
            path="metrics v3",
            kind="calculation",
            started_at=world.clock.now(),
        )
    ]


@pytest.mark.parametrize("state", ["queued", "failed", "done"])
def test_a_calculation_that_is_not_running_is_not_working(state: str) -> None:
    world, calculations = with_calculation(state)

    assert (
        working_steps(world.ports.runs, world.ports.steps, world.ports.attempts, calculations) == []
    )


def test_a_calculation_of_a_vanished_run_is_ignored() -> None:
    world, calculations = with_calculation("running")
    world.ports.runs.runs.clear()  # type: ignore[attr-defined]

    assert (
        working_steps(world.ports.runs, world.ports.steps, world.ports.attempts, calculations) == []
    )


def test_a_running_calculation_refuses_the_hold() -> None:
    world, calculations = with_calculation("running")
    holds = FakeInstanceHoldRepository()
    ports = HoldPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        holds=holds,
        uow=FakeUnitOfWork(),
        clock=world.clock,
        calculations=calculations,
    )

    with pytest.raises(HoldRefused) as refused:
        place_hold(ports, 600, "upgrade")

    assert [(s.kind, s.path) for s in refused.value.working] == [("calculation", "metrics v3")]
    assert holds.hold is None


def test_the_activity_read_lists_the_same_working_step() -> None:
    world, calculations = with_calculation("running")
    ports = ActivityPorts(
        queue=QueuePorts(
            engine=FakeWorkflowEngine(clock=world.clock),
            runs=world.ports.runs,
            steps=world.ports.steps,
            clock=world.clock,
            max_active_runs=2,
        ),
        attempts=world.ports.attempts,
        dbos_application_version="1",
        calculations=calculations,
    )

    activity = read_activity(ports)

    assert [(s.kind, s.path) for s in activity.working] == [("calculation", "metrics v3")]
