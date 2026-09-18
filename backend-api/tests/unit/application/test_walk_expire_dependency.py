"""`walk.expire` guard for dependency-parked Runs (story 5-4).

A `needs_you` Run with `park_kind="dependency"` must absorb the recv-expiry deadline without
a status transition (the Run was never dispatched to the engine, so there is no recv timeout
that fires for it — the deadline call is a no-op).
"""

from __future__ import annotations

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.walk import WalkPorts, expire
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit


def ports_of(world) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )


def test_expire_dependency_park_returns_current_status_without_transitioning() -> None:
    """expire() on a dependency-parked Run returns 'needs_you' and writes nothing."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    result = expire(ports_of(world), world.run.id)

    assert result == "needs_you"
    # The Run must remain needs_you — not failed.
    stored = world.stored_run()
    assert stored.status == "needs_you"
    assert stored.park_kind == "dependency"


def test_expire_dependency_park_does_not_write_a_gate_record() -> None:
    """expire() on a dependency-parked Run must not append a gate record."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    expire(ports_of(world), world.run.id)

    assert world.records() == []


def test_expire_dependency_park_does_not_commit_the_uow() -> None:
    """expire() on a dependency-parked Run exits the UoW guard early — no commit."""
    world = a_world(
        "needs_you",
        PAIR_PLAN,
        park_kind="dependency",
        park_path=None,
        park_reason="run abc ended failed",
    )

    expire(ports_of(world), world.run.id)

    # The UoW was never committed (no writes happened inside it).
    assert not world.ports.uow.committed
