"""`place_hold`, `release_hold`, `hold_active` (SPEC CAP-4, AD-30) over the shared fakes."""

from __future__ import annotations

from datetime import timedelta

import pytest

from orchestrator.application.use_cases.instance_hold import (
    HoldPorts,
    HoldRefused,
    hold_active,
    place_hold,
    release_hold,
)
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import World, a_world, an_attempt
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository


def hold_ports(world: World, holds: FakeInstanceHoldRepository) -> HoldPorts:
    return HoldPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        holds=holds,
        uow=FakeUnitOfWork(),
        clock=world.clock,
    )


def a_hold(world: World, **over: object) -> InstanceHold:
    fields: dict[str, object] = {
        "id": new_id(),
        "held_at": world.clock.now(),
        "expires_at": world.clock.now() + timedelta(minutes=5),
        "reason": "old",
    }
    fields.update(over)
    return InstanceHold(**fields)  # type: ignore[arg-type]


def test_a_working_step_refuses_the_hold_and_writes_nothing() -> None:
    world = a_world("running", statuses={"baseline": "running"})
    an_attempt(world, "plan", role="session")
    holds = FakeInstanceHoldRepository()
    ports = hold_ports(world, holds)

    with pytest.raises(HoldRefused) as refused:
        place_hold(ports, 600, "upgrade")

    assert sorted(step.kind for step in refused.value.working) == ["session", "shell"]
    assert holds.calls == ["get_for_update"]
    assert holds.hold is None
    assert isinstance(ports.uow, FakeUnitOfWork)
    assert ports.uow.committed is False
    assert "2 working steps" in str(refused.value)


def test_no_working_step_stores_the_hold_and_commits() -> None:
    world = a_world("running")
    holds = FakeInstanceHoldRepository()
    ports = hold_ports(world, holds)

    hold = place_hold(ports, 600, "upgrade")

    assert hold.held_at == world.clock.now()
    assert hold.expires_at == world.clock.now() + timedelta(seconds=600)
    assert hold.reason == "upgrade"
    assert holds.hold == hold
    assert isinstance(ports.uow, FakeUnitOfWork)
    assert ports.uow.committed is True


def test_a_second_hold_replaces_the_expiry_and_keeps_the_stored_id() -> None:
    world = a_world("running")
    stored = a_hold(world)
    holds = FakeInstanceHoldRepository(stored)
    world.clock.advance(30)

    hold = place_hold(hold_ports(world, holds), 60, "again")

    assert hold.id == stored.id
    assert hold.expires_at == world.clock.now() + timedelta(seconds=60)
    assert holds.hold == hold


def test_release_deletes_and_commits_with_or_without_a_hold() -> None:
    world = a_world("running")
    for stored in (a_hold(world), None):
        holds = FakeInstanceHoldRepository(stored)
        uow = FakeUnitOfWork()

        release_hold(holds, uow)

        assert holds.hold is None
        assert holds.calls == ["delete_all"]
        assert uow.committed is True


def test_hold_active_reads_the_shared_lock_only_with_a_repository() -> None:
    world = a_world("running")
    now = world.clock.now()
    assert hold_active(None, now) is False

    none = FakeInstanceHoldRepository()
    assert hold_active(none, now) is False
    assert none.calls == ["get_shared"]

    assert hold_active(FakeInstanceHoldRepository(a_hold(world)), now) is True
    expired = a_hold(world, expires_at=now)
    assert hold_active(FakeInstanceHoldRepository(expired), now) is False
