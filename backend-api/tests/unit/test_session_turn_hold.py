"""A senior session turn waits on an instance hold (SPEC CAP-4, AD-30)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta

from orchestrator.application.use_cases.session_turn import run_turn
from orchestrator.application.use_cases.walk import HELD
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.dbos.session_walker import build_session_turn
from orchestrator.infrastructure.dbos.walker import WalkerDeps
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository


def hold_the(world: TurnWorld) -> FakeInstanceHoldRepository:
    now = world.session.world.clock.now()
    holds = FakeInstanceHoldRepository(
        InstanceHold(id=new_id(), held_at=now, expires_at=now + timedelta(days=1), reason="upgrade")
    )
    world.session.world.ports = replace(world.writers, holds=holds)
    return holds


def test_a_held_turn_stays_queued_and_dispatches_after_the_hold() -> None:
    world = a_turn_world()
    holds = hold_the(world)
    posted = world.post()

    assert run_turn(world.ports, posted.attempt_id) is HELD

    before = world.attempt(posted.attempt_id)
    assert before.status == "queued"
    assert world.harness.called("start") == []
    holds.delete_all()
    assert run_turn(world.ports, posted.attempt_id) is None
    assert len(world.harness.called("start")) == 1


def test_the_session_step_sleeps_between_polls_and_stays_two_steps() -> None:
    world = a_turn_world()
    holds = hold_the(world)
    posted = world.post()
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        holds.delete_all()

    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.writers

    engine = FakeDurableEngine()
    turn = build_session_turn(
        engine,
        WalkerDeps(
            open_ports=open_ports,
            step_ports=world.step,
            human_wait_seconds=5,
            read_environment=world._environment,
            sleep=sleep,
        ),
    )

    turn(str(posted.attempt_id))

    assert sleeps == [5]
    assert holds.calls.count("get_shared") == 2  # noqa: PLR2004
    assert world.attempt(posted.attempt_id).status == "done"
    assert [name for kind, name in engine.declared if kind == "step"] == [
        "session_turn",
        "session_commit",
    ]
