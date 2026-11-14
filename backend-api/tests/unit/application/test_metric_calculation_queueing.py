"""A write that ends a Run queues its metrics calculation in the same unit of work and tells
the engine only after the commit (epic 2 story 5: AC1, AC2 queueing half)."""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.metric_calculations import (
    enqueue_queued,
    queue_terminal_calculation,
)
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.walk import WalkPorts, close_run, expire
from orchestrator.application.use_cases.writers import finish_run
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.metric_results import (
    FakeMetricCalculationRepository,
    FakeResultVersionRepository,
)

TWO = 2


def wired(world: World) -> tuple[World, FakeMetricCalculationRepository]:
    calculations = FakeMetricCalculationRepository()
    ports = replace(
        world.ports,
        engine=world.engine,
        calculations=calculations,
        versions=FakeResultVersionRepository(),
    )
    return replace(world, ports=ports), calculations


def walk_ports(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )


def test_closing_a_run_queues_one_calculation_in_its_unit_and_enqueues_after_commit() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}))

    assert close_run(walk_ports(world), world.run.id) == "done"

    [queued] = calculations.rows
    assert (queued.run_id, queued.target_n, queued.state) == (world.run.id, 1, "queued")
    assert queued.entry_point == ("at_attempt_end",)
    assert queued.queued_at == world.clock.now()
    assert world.engine.calls == [("enqueue_calculation", queued.id)]
    assert world.engine.committed_when_called == [True]


def test_the_row_is_added_while_the_unit_is_still_uncommitted() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}))
    seen: list[bool] = []
    original = calculations.add
    calculations.add = lambda c: (seen.append(world.ports.uow.committed), original(c))[1]  # type: ignore[method-assign]

    close_run(walk_ports(world), world.run.id)

    assert seen == [False]


def test_a_cancel_queues_the_calculation_and_enqueues_it_after_the_commit() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "running"}))

    outcome = signal_run(
        SignalPorts(writers=world.ports, engine=world.engine), world.run.id, Signal(kind="cancel")
    )

    assert outcome.run.status == "cancelled"
    [queued] = calculations.rows
    assert queued.target_n == 1
    assert ("enqueue_calculation", queued.id) in world.engine.calls
    assert world.engine.calls.index(("enqueue_calculation", queued.id)) > 0


def test_a_cancel_through_writers_without_an_engine_still_enqueues_on_the_signal_engine() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "running"}))
    writers = replace(world.ports, engine=None)

    signal_run(
        SignalPorts(writers=writers, engine=world.engine), world.run.id, Signal(kind="cancel")
    )

    [queued] = calculations.rows
    assert ("enqueue_calculation", queued.id) in world.engine.calls


def test_an_expired_park_queues_and_enqueues() -> None:
    world, calculations = wired(a_world("needs_you", PAIR_PLAN, park_kind="internal"))

    assert expire(walk_ports(world), world.run.id) == "failed"

    [queued] = calculations.rows
    assert world.engine.calls == [("enqueue_calculation", queued.id)]


def test_a_second_write_on_an_ended_run_queues_nothing_more() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}))
    close_run(walk_ports(world), world.run.id)
    ended = world.stored_run()

    with world.ports.uow:
        queue_terminal_calculation(calculations, world.ports.versions, world.clock, ended, ended)

    assert len(calculations.rows) == 1


def test_the_next_calculation_targets_the_next_version() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}))
    versions = world.ports.versions
    assert versions is not None
    run = world.run
    ended = run.model_copy(update={"status": "done"})

    versions.add(
        ResultVersion(
            id=new_id(),
            run_id=run.id,
            n=1,
            calculated_at=EPOCH,
            entry_point=("manual",),
            methods=(),
        ),
        [],
    )

    queue_terminal_calculation(calculations, versions, world.clock, run, ended)

    assert calculations.rows[0].target_n == TWO


def test_nothing_is_queued_or_enqueued_when_the_repositories_are_not_wired() -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"})
    plain = replace(world, ports=replace(world.ports, engine=world.engine))

    assert close_run(walk_ports(plain), plain.run.id) == "done"

    assert plain.engine.calls == []


def test_a_live_run_enqueues_nothing() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN))

    enqueue_queued(world.engine, calculations, world.run)

    assert world.engine.calls == []


def test_a_terminal_write_racing_a_committed_cancel_queues_no_second_calculation() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN))
    stale = world.run
    with world.ports.uow:
        finish_run(world.ports, world.run)

    with world.ports.uow:
        finish_run(world.ports, stale)

    assert len(calculations.rows) == 1


def test_finish_run_alone_adds_the_row_in_the_callers_unit() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN))

    with world.ports.uow:
        finish_run(world.ports, world.run)

    assert len(calculations.rows) == 1
    assert world.engine.calls == []


def test_an_already_enqueued_or_running_calculation_is_not_enqueued_again() -> None:
    world, calculations = wired(a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "done"}))
    close_run(walk_ports(world), world.run.id)
    calculations.set(calculations.rows[0].model_copy(update={"state": "running"}))

    enqueue_queued(world.engine, calculations, world.stored_run())

    assert len(world.engine.calls) == 1
