"""Asking for a calculation by hand, and the start-up net (epic 2 story 5: AC3, AC4, AC7)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.metric_calculations import (
    CalculatePorts,
    request_calculation,
    sweep_calculations,
)
from orchestrator.domain.entities.metric_results import MetricCalculation, ResultVersion
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.metric_results import (
    FakeMetricCalculationRepository,
    FakeResultVersionRepository,
)


def a_request(status: str = "done") -> tuple[CalculatePorts, World]:
    world = a_world(status, PAIR_PLAN)  # type: ignore[arg-type]
    uow = FakeUnitOfWork()
    engine = FakeWorkflowEngine(clock=world.clock, uow=uow)
    ports = CalculatePorts(
        runs=world.ports.runs,
        calculations=FakeMetricCalculationRepository(),
        versions=FakeResultVersionRepository(),
        engine=engine,
        clock=world.clock,
        uow=uow,
    )
    return ports, world


def a_version(ports: CalculatePorts, world: World, n: int = 1) -> None:
    ports.versions.add(
        ResultVersion(
            id=new_id(),
            run_id=world.run.id,
            n=n,
            calculated_at=world.clock.now(),
            entry_point=("at_attempt_end",),
            methods=(),
        ),
        [],
    )


def test_a_manual_calculation_targets_the_next_version_and_is_enqueued_after_commit() -> None:
    ports, world = a_request()
    a_version(ports, world)

    calculation = request_calculation(ports, world.run.id)

    assert (calculation.target_n, calculation.state) == (2, "queued")
    assert calculation.entry_point == ("manual",)
    assert ports.engine.calls == [("enqueue_calculation", calculation.id)]  # type: ignore[attr-defined]
    assert ports.engine.committed_when_called == [True]  # type: ignore[attr-defined]


@pytest.mark.parametrize("state", ["queued", "running"])
def test_a_calculation_in_progress_refuses_another(state: str) -> None:
    ports, world = a_request()
    ports.calculations.add(
        MetricCalculation(
            id=new_id(),
            run_id=world.run.id,
            target_n=1,
            state=state,  # type: ignore[arg-type]
            entry_point=("at_attempt_end",),
            queued_at=world.clock.now(),
        )
    )

    with pytest.raises(Conflict, match=f"calculation v1 is {state}"):
        request_calculation(ports, world.run.id)

    assert len(ports.calculations.rows) == 1  # type: ignore[attr-defined]
    assert ports.engine.calls == []  # type: ignore[attr-defined]


@pytest.mark.parametrize("status", ["queued", "running", "needs_you"])
def test_a_live_run_refuses(status: str) -> None:
    ports, world = a_request(status)

    with pytest.raises(Conflict, match="metrics are calculated on an ended Run"):
        request_calculation(ports, world.run.id)

    assert ports.calculations.rows == []  # type: ignore[attr-defined]


def test_an_unknown_run_is_not_found() -> None:
    ports, _world = a_request()

    with pytest.raises(NotFound):
        request_calculation(ports, new_id())


def calc(state: str, world: World) -> MetricCalculation:
    return MetricCalculation(
        id=new_id(),
        run_id=world.run.id,
        target_n=1,
        state=state,  # type: ignore[arg-type]
        entry_point=("manual",),
        queued_at=world.clock.now(),
    )


def test_the_sweep_fails_a_running_calculation_the_engine_does_not_hold() -> None:
    ports, world = a_request()
    lost, kept = calc("running", world), calc("running", world)
    ports.calculations.add(lost)
    ports.calculations.add(kept)

    sweep_calculations(
        ports.calculations, ports.uow, ports.clock, ports.engine, frozenset({kept.id})
    )

    failed = ports.calculations.get(lost.id)
    assert failed is not None
    assert (failed.state, failed.output, failed.ended_at) == (
        "failed",
        "interrupted",
        world.clock.now(),
    )
    still = ports.calculations.get(kept.id)
    assert still is not None and still.state == "running"
    assert ports.versions.list_for_run(world.run.id) == []


def test_the_sweep_enqueues_a_queued_calculation_the_engine_does_not_hold() -> None:
    ports, world = a_request()
    orphan, held = calc("queued", world), calc("queued", world)
    ports.calculations.add(orphan)
    ports.calculations.add(held)

    sweep_calculations(
        ports.calculations, ports.uow, ports.clock, ports.engine, frozenset({held.id})
    )

    assert ports.engine.calls == [("enqueue_calculation", orphan.id)]  # type: ignore[attr-defined]
