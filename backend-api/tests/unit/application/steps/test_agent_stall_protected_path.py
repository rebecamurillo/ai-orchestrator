"""FR-10, FR-31, operator revision 2026-09-15: the stall detector checks protected anchors
before reporting a stall, so a modified anchor overrides the stall park.

This covers the `result.stalled and hit is not None` branch of `agent_tail.finish` —
the same guarantee `test_agent_protected_paths.py` provides for the wall-clock timeout path.
The rule (FR-31: a modified anchor wins over every route) applies to stalls too.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_tail import PROTECTED
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.steps.agent_fixtures import HEAD_SHA, WORKTREE, World
from tests.unit.application.steps.agent_tail_fixtures import END_SHA, LOG_PATH, a_tail_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

WORKTREE_PATH = Path(WORKTREE)
SPEC_FOLDER = "specs/notifications"
SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
STORIES_YAML = f"{SPEC_FOLDER}/stories.yaml"
ANCHORS = frozenset({SPEC_MD, STORIES_YAML})


def _a_git(*changes: Change) -> FakeGit:
    return FakeGit(
        status=[""],
        head_sha=[HEAD_SHA, END_SHA],
        diff_changes=[tuple(changes)],
    )


def _a_stalled_world(*changes: Change, **over: Any) -> World:
    """A stalled dispatch over a range that touched `changes`, with anchors wired."""
    harness = FakeHarness()
    harness.results.append(
        HarnessResult(
            session_id="s-1",
            exit_code=None,
            stalled=True,
            stall_cwd=WORKTREE_PATH,
            log_path=LOG_PATH,
        )
    )
    world = a_tail_world(harness=harness, git=_a_git(*changes), **over)
    env = world.ctx.ports.run_env
    assert env is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(
            world.ctx.ports,
            run_env=replace(env, anchors=ANCHORS, accepted_paths=()),
        ),
    )
    return world


def test_a_dispatch_that_edited_an_anchor_and_then_stalled_parks_on_the_anchor() -> None:
    """FR-31: a modified anchor wins over the stall park (same guarantee as for wall-clock
    timeout — operator revision 2026-09-15 extended the check to the stall path)."""
    world = _a_stalled_world(Change(path=SPEC_MD, kind="modified"))

    result = AgentExecutor().execute(world.ctx)

    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == PROTECTED.format(paths=SPEC_MD)
    assert result.output_ref == str(LOG_PATH)
