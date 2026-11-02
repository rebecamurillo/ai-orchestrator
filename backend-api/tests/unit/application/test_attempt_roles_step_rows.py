"""Attempt roles on the Run detail's step rows and checkpoint story (story 1-7, AD-21, 2026-11-01).

A step row's `latest` attempt and its attempt count read `agent` attempts only: the Answer hint
numbers its archive off `latest.n`, and the diagram counts retries off `attempts`. Its cost
stays the sum over every role. A done checkpoint's "N attempts" counts the build's `agent`
attempts only.
"""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.run_views import RunViewPorts, StepRowView, run_detail
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

BUILD = "stories[1].build"
AFTER = "stories[1].after"
AGENT_MODEL = "agent-model"
CONSULT_MODEL = "senior-model"
AGENT_COST = Decimal("1.50")
CONSULT_COST = Decimal("0.25")


def a_world_with_a_consult(second_role: str = "consult", **over: object) -> World:
    world = a_world("needs_you", EPIC_PLAN, {BUILD: "done", AFTER: "checkpoint"}, **over)
    an_attempt(world, BUILD, n=1, status="done", model=AGENT_MODEL, cost_usd=AGENT_COST)
    an_attempt(
        world,
        BUILD,
        n=2,
        role=second_role,
        status="done",
        model=CONSULT_MODEL,
        cost_usd=CONSULT_COST,
    )
    return world


def view_ports(world: World) -> RunViewPorts:
    return RunViewPorts(
        runs=world.ports.runs,
        steps=world.ports.steps,
        attempts=world.ports.attempts,
        gate_records=world.ports.records,
        projects=FakeProjectRepository([]),
        repositories=FakeRepositoryRepository([]),
        logs=FakeLogReader(),
        clock=world.clock,
    )


def build_row_of(world: World) -> StepRowView:
    detail = run_detail(view_ports(world), world.run.id)
    return next(step for step in detail.steps if step.path == BUILD)


def test_a_step_row_s_latest_and_count_read_agent_attempts_only() -> None:
    step = build_row_of(a_world_with_a_consult())

    assert step.attempts == 1
    assert step.latest is not None
    assert (step.latest.n, step.latest.model) == (1, AGENT_MODEL)


def test_a_step_row_s_cost_sums_every_role() -> None:
    step = build_row_of(a_world_with_a_consult())

    assert step.cost_usd == AGENT_COST + CONSULT_COST


def test_a_step_row_with_only_agent_attempts_is_unchanged() -> None:
    step = build_row_of(a_world_with_a_consult("agent"))

    assert step.attempts == 2  # noqa: PLR2004
    assert step.latest is not None
    assert step.latest.model == CONSULT_MODEL


def test_a_done_checkpoint_counts_the_build_s_agent_attempts_only() -> None:
    world = a_world_with_a_consult(park_kind="checkpoint", park_path=AFTER)

    detail = run_detail(view_ports(world), world.run.id)

    assert detail.alert is not None
    assert detail.alert.checkpoint_story is not None
    assert detail.alert.checkpoint_story.attempts == 1
    assert detail.alert.checkpoint_story.cost_usd == AGENT_COST + CONSULT_COST
