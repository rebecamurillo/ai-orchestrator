"""`steps/agent_env.py`: what one dispatch hands its harness process — the agent's and the
senior's alike (AD-5, AD-10, AD-11)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.application.steps import agent_env
from tests.unit.application.steps.agent_fixtures import (
    PROJECT_SLUG,
    STORY_ID,
    WORKTREE,
    a_run,
    a_world,
)


def test_the_environment_is_exactly_what_the_builder_returned() -> None:
    world = a_world()

    env = agent_env.environment(world.ctx, world.attempt, "00-trace-span-01")

    [call] = world.harness_env.calls
    assert call["attempt"] == world.attempt
    assert call["project_slug"] == PROJECT_SLUG
    assert call["story_id"] == STORY_ID
    assert call["traceparent"] == "00-trace-span-01"
    assert env["TRACEPARENT"] == "00-trace-span-01"


def test_a_row_with_no_story_hands_none() -> None:
    world = a_world(with_resolved={"harness": "claude", "story_id": ""})

    agent_env.environment(world.ctx, world.attempt, "")

    assert world.harness_env.calls[0]["story_id"] is None


def test_the_remaining_budget_is_budget_less_spend_or_none_without_one() -> None:
    assert agent_env.remaining(
        a_run(budget_usd=Decimal("10"), spend_usd=Decimal("4"), gate_spend_usd=Decimal("4"))
    ) == Decimal("6")
    assert agent_env.remaining(a_run(budget_usd=None)) is None


def test_the_hub_root_is_added_only_when_the_dispatch_stands_elsewhere() -> None:
    world = a_world()

    assert agent_env.add_dirs(world.ctx, Path(WORKTREE)) == ()
    assert agent_env.add_dirs(world.ctx, Path(WORKTREE) / "repos/m") == (Path(WORKTREE),)
