"""`agent_recheck.re_check` (AD-9, AD-17; story 1-8, 2026-11-02): an Operator's `continue` or a
senior's `senior_accept`, carrying files, re-runs the tail over the previous attempt and
dispatches nothing. Every other resume is the ordinary dispatch (`None`)."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.steps import agent_recheck
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    World,
    a_gate_record,
    an_agent_row,
)
from tests.unit.application.steps.agent_tail_fixtures import END_SHA, LOG_PATH
from tests.unit.application.steps.test_agent_protected_paths import (
    FROZEN_TEST,
    WORKTREE_PATH,
    a_git,
    a_previous,
    a_protected_world,
)


def resumed(event: str, payload: dict[str, Any], **over: Any) -> World:
    fields: dict[str, Any] = {
        "accepted": (FROZEN_TEST,),
        "previous": a_previous(),
        "resume": a_gate_record(an_agent_row(), event, payload),  # type: ignore[arg-type]
        "git": a_git(Change(path=FROZEN_TEST, kind="modified")),
    }
    fields.update(over)
    return a_protected_world(**fields)


@pytest.mark.parametrize("event", ["continue", "senior_accept"])
def test_an_accepting_record_re_checks_the_previous_range_dispatching_nothing(event: str) -> None:
    world = resumed(event, {"files": [FROZEN_TEST], "kind": "protected_path"})

    result = agent_recheck.re_check(world.ctx)

    assert result == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))
    assert world.harness.calls == []
    assert world.git.called("diff_changes") == [(WORKTREE_PATH, HEAD_SHA, END_SHA)]


@pytest.mark.parametrize(
    ("event", "payload"),
    [("senior_accept", {}), ("continue", {"files": []}), ("senior_answer", {"files": ["x"]})],
    ids=["acceptance without files", "continue without files", "another record"],
)
def test_every_other_resume_is_the_ordinary_dispatch(event: str, payload: dict[str, Any]) -> None:
    assert agent_recheck.re_check(resumed(event, payload).ctx) is None


def test_no_previous_attempt_is_the_ordinary_dispatch() -> None:
    world = resumed("senior_accept", {"files": [FROZEN_TEST]}, previous=None)

    assert agent_recheck.re_check(world.ctx) is None


def test_no_resume_is_the_ordinary_dispatch() -> None:
    world = resumed("senior_accept", {"files": [FROZEN_TEST]}, resume=None)

    assert agent_recheck.re_check(world.ctx) is None


def test_the_accepting_events_are_the_operators_and_the_seniors() -> None:
    assert frozenset({"continue", "senior_accept"}) == agent_recheck.ACCEPTING_EVENTS
