"""`walk.apply_result` always binds `apply_step_result`'s `after_route` to
`budget_second_record` (5.7) — proven at this level, not only at `budget_second_record`'s
own, because a dropped line in `_budget_hook` would leave every over-budget stop that
parked on its own reason with no second `budget` record and nothing else would fail.
"""

from __future__ import annotations

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.walk import WalkPorts, apply_result
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"

BUDGET_PARK = Park(kind="budget", reason="budget $41.20 / $40.00")


def a_pair(**over: object) -> World:
    return a_world("running", PAIR_PLAN, {"plan": "running"}, **over)


def ports_of(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )


def test_apply_result_writes_the_second_budget_record_on_its_own() -> None:
    world = a_pair()
    blocked = StepResult(
        status="blocked",
        gate="deterministic",
        park=Park(kind="blocked", reason="ask", path="plan"),
        budget_park=BUDGET_PARK,
    )

    status = apply_result(ports_of(world), world.run.id, 1, blocked)

    assert status == "needs_you"
    assert world.stored_run().park_kind == "budget"
    assert world.events() == ["blocked", "budget"]


def test_apply_result_adds_nothing_when_the_result_carries_no_budget_park() -> None:
    world = a_pair()
    blocked = StepResult(
        status="blocked", gate="deterministic", park=Park(kind="blocked", reason="ask")
    )

    apply_result(ports_of(world), world.run.id, 1, blocked)

    assert world.stored_run().park_kind == "blocked"
    assert world.events() == ["blocked"]
