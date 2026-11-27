"""`retry_budget_advances` and `set_run_defaults(..., retry=...)` (epic 8 story 3, AC8)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from orchestrator.application.use_cases.advance_retry import (
    AdvanceRetryPorts,
    retry_budget_advances,
)
from orchestrator.application.use_cases.initiative_advance import advance_initiative
from orchestrator.application.use_cases.project_run_defaults import RunDefaults, set_run_defaults
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.initiative_advance import InitiativeAdvance
from orchestrator.domain.ids import new_id
from tests.unit.application.initiative_transition_world import PROJECT_BUDGET, TransitionWorld
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine

NO_BUDGET = "no project budget"


class Retry:
    """The retry ports' own unit of work and engine, as the router's provider builds them."""

    def __init__(self, world: TransitionWorld) -> None:
        self.uow = FakeUnitOfWork()
        self.engine = FakeWorkflowEngine(clock=FakeClock(), uow=self.uow)
        self.ports = AdvanceRetryPorts(
            initiatives=world.initiatives,
            advances=world.advances,
            uow=self.uow,
            engine=self.engine,
        )


def project_ports(world: TransitionWorld) -> ProjectPorts:
    return ProjectPorts(
        uow=world.uow,
        projects=world.projects,
        crypto=FakeCrypto(),
        clock=world.harness.clock,
    )


def defaults(budget: Decimal | None) -> RunDefaults:
    return RunDefaults(
        default_budget_usd=budget,
        default_harness="claude",
        default_model="sonnet",
        default_autonomy=None,
        default_senior_model=None,
    )


def blocked_merge(world: TransitionWorld, reason: str | None = NO_BUDGET) -> InitiativeAdvance:
    world.defaults(default_budget_usd=None)
    advance = world.advance_of(world.ended_run(1))
    advance_initiative(world.advance_ports(), advance.id)
    stored = world.advances.advances[-1]
    assert stored.blocked_reason == NO_BUDGET
    if reason != NO_BUDGET:
        stored = stored.model_copy(update={"blocked_reason": reason})
        world.advances.update(stored)
    return stored


def stored(world: TransitionWorld, advance: InitiativeAdvance) -> InitiativeAdvance:
    return next(a for a in world.advances.advances if a.id == advance.id)


def enqueued(retry: Retry) -> list[Any]:
    return [args for name, args in retry.engine.calls if name == "enqueue_advance"]


def test_a_budget_blocked_advance_is_cleared_then_enqueued_after_the_commit() -> None:
    world = TransitionWorld()
    advance = blocked_merge(world)
    retry = Retry(world)

    cleared = retry_budget_advances(retry.ports, world.project.id)

    assert cleared == [advance.id]
    assert stored(world, advance).blocked_reason is None
    assert enqueued(retry) == [advance.id]
    assert retry.engine.committed_when_called == [True]


def test_any_other_blocked_reason_is_not_touched() -> None:
    world = TransitionWorld()
    advance = blocked_merge(world, reason="no gate verdict")
    retry = Retry(world)

    assert retry_budget_advances(retry.ports, world.project.id) == []

    assert stored(world, advance).blocked_reason == "no gate verdict"
    assert enqueued(retry) == []


def test_a_consumed_advance_is_not_touched() -> None:
    world = TransitionWorld()
    advance = blocked_merge(world)
    world.advances.update(advance.model_copy(update={"consumed_at": world.harness.clock.now()}))

    assert retry_budget_advances(Retry(world).ports, world.project.id) == []


def test_another_projects_advance_is_not_touched() -> None:
    world = TransitionWorld()
    blocked_merge(world)

    assert retry_budget_advances(Retry(world).ports, new_id()) == []


def test_setting_the_budget_wakes_the_advance_and_running_it_creates_the_build() -> None:
    world = TransitionWorld()
    world.spec_branch(epics=True)
    advance = blocked_merge(world)
    retry = Retry(world)

    with world.uow:
        set_run_defaults(
            project_ports(world), world.project.id, defaults(PROJECT_BUDGET), retry.ports
        )

    assert stored(world, advance).blocked_reason is None
    assert enqueued(retry) == [advance.id]
    advance_initiative(world.advance_ports(), advance.id)
    assert stored(world, advance).consumed_at is not None
    builds = [r for r in world.runs.runs.values() if r.initiative_position == 2]  # noqa: PLR2004
    assert [r.budget_usd for r in builds] == [PROJECT_BUDGET]


def test_without_retry_ports_the_defaults_are_saved_and_nothing_is_woken() -> None:
    world = TransitionWorld()
    advance = blocked_merge(world)

    with world.uow:
        set_run_defaults(project_ports(world), world.project.id, defaults(PROJECT_BUDGET))

    assert stored(world, advance).blocked_reason == NO_BUDGET
