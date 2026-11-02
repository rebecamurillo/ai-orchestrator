"""`agent_consult_senior` (AD-10/AD-14/AD-22, split out of `agent_consult.py` by story 1-8 on
2026-11-02): the senior starts in a new session on its own block's limits, its group is
committed before it is awaited, and the attempt is finished with what it reported."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.application.steps import agent_consult_senior
from tests.unit.application.consult_fixtures import (
    AGENT_SESSION,
    CONSULT_LOG,
    World,
    a_consult_world,
)
from tests.unit.application.steps.agent_fixtures import WORKTREE

TIMEOUT_MIN = 5
ROW_STALL_MIN = 30


def a_senior(world: World) -> agent_consult_senior.Senior:
    return agent_consult_senior.Senior(
        harness=world.harness,
        started=world.attempt,
        prompt="Review it.",
        tree=Path(WORKTREE),
        block={"timeout_min": TIMEOUT_MIN},
    )


def test_the_senior_starts_in_a_new_session_on_its_blocks_timeout() -> None:
    world = a_consult_world()

    result, spent = agent_consult_senior.dispatch(world.ctx, a_senior(world))

    [start] = world.harness.called("start")
    assert start["session_id"] != AGENT_SESSION
    assert start["timeout_min"] == TIMEOUT_MIN
    assert start["prompt"] == "Review it."
    assert result.log_path == CONSULT_LOG
    assert spent is None
    finished = world.attempts.attempts[world.attempt.id]
    assert finished.exit_code == 0
    assert finished.log_path == str(CONSULT_LOG)


def test_the_stall_limit_is_the_rows_or_the_kinds_default() -> None:
    world = a_consult_world()
    undeclared = replace(world.ctx, with_resolved={})

    assert agent_consult_senior.stall_min(world.ctx) == ROW_STALL_MIN
    assert agent_consult_senior.stall_min(undeclared) == agent_consult_senior.DEFAULT_STALL_MIN
