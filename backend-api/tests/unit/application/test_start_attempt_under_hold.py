"""`start_attempt` and `walk.attempt_row` while the instance is held (SPEC CAP-4, AD-30)."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.application.use_cases.walk import HELD, WalkPorts, attempt_row
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository


class Done:
    def execute(self, ctx: StepContext) -> StepResult:
        return StepResult(status="done", gate=ctx.row.gate)


def a_hold(world: World, *, ttl: int = 600) -> InstanceHold:
    now = world.clock.now()
    return InstanceHold(
        id=new_id(), held_at=now, expires_at=now + timedelta(seconds=ttl), reason="upgrade"
    )


def held(world: World, hold: InstanceHold | None) -> tuple[WalkPorts, FakeInstanceHoldRepository]:
    holds = FakeInstanceHoldRepository(hold)
    writers = replace(world.ports, holds=holds)
    step = StepPorts(git=FakeGit(), clock=world.clock, work_dir="/work")
    return WalkPorts(writers=writers, step=step), holds


def test_an_active_hold_returns_held_and_writes_nothing() -> None:
    world = a_world("queued", PAIR_PLAN, statuses={"plan": "queued"})
    ports, holds = held(world, a_hold(world))

    assert attempt_row(ports, world.run.id, 1, {}) is HELD

    assert holds.calls == ["get_shared"]
    assert world.attempts_of("plan") == []
    assert world.status_of("plan") == "queued"
    assert world.stored_run().status == "queued"
    assert world.records() == []
    assert isinstance(ports.writers.uow, FakeUnitOfWork)
    assert ports.writers.uow.committed is False


def test_start_attempt_answers_none_when_held() -> None:
    world = a_world("queued", PAIR_PLAN, statuses={"plan": "queued"})
    ports, _ = held(world, a_hold(world))

    assert start_attempt(ports.writers, world.run.id, 1) is None


def test_a_deleted_hold_expired_hold_or_no_repository_starts_attempt_one() -> None:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    register("plan.check", Done())
    try:
        for hold_of in (
            lambda w: None,
            lambda w: a_hold(w, ttl=0),
            lambda w: a_hold(w, ttl=-5),
        ):
            world = a_world("queued", PAIR_PLAN, statuses={"plan": "queued"})
            ports, _ = held(world, hold_of(world))

            result = attempt_row(ports, world.run.id, 1, {})

            assert isinstance(result, StepResult)
            assert [a.n for a in world.attempts_of("plan")] == [1]
        world = a_world("queued", PAIR_PLAN, statuses={"plan": "queued"})
        no_repository = WalkPorts(
            writers=world.ports,
            step=StepPorts(git=FakeGit(), clock=world.clock, work_dir="/work"),
        )
        assert isinstance(attempt_row(no_repository, world.run.id, 1, {}), StepResult)
    finally:
        EXECUTORS.clear()
        EXECUTORS.update(kept)
