"""One wired world for the `agent` kind's *tail*: the dispatch world plus a Story file.

Built on `agent_fixtures.py` by import and never by copy — the row, the ports and the three
recorders are that module's, and the only thing added here is what FR-16 routes on: a Story
file in the worktree, the `expect` / `retry` contract the planner flattens onto a real
`agent` row (`application/templates/agent_row.py`), and a scripted harness exit.

**Why `contracted()` exists beside `resolved()`.** `agent_fixtures.resolved()` is the row as
the dispatch half needs it, and it predates the contract: it carries no `expect` and no
`retry`, which is exactly a row with no liveness contract to evaluate. Every test about the
FR-16 table wants the row the planner really writes, so it takes this one.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.application.steps.context import StepContext
from orchestrator.application.templates.agent_row import EXPECT_KEY, RETRY_KEY
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    SPEC_FOLDER,
    STORY_ID,
    World,
    a_world,
    resolved,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

#: Where a Story's file lives, and the glob `templates/story.yaml` declares over it.
STORIES = f"{SPEC_FOLDER}/stories"
STORY_GLOB = f"{STORIES}/{STORY_ID}-*.md"
STORY_PATH = f"{STORIES}/{STORY_ID}-notify.md"
OTHER_PATH = f"{STORIES}/{STORY_ID}-other.md"
#: Where FR-18 and AD-13 archive a Story file that is in the way.
ANSWERS = f"{STORIES}/.answers"
#: The document `_prepare_writes` always writes when the row names a spec folder (FR-15).
CONTEXT_FILE = f"{SPEC_FOLDER}/project-context.md"

#: The shipped `retry` contract of `templates/story.yaml`, shortened.
RETRY_PROMPT = "Finish the story and write that file."
RETRY_MAX = 2

#: What the scripted harness reports, and the HEAD the dispatch moves to.
LOG_PATH = Path("/work/logs/003-1.log")
SESSION_ID = "s-1"
END_SHA = "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d"

AUTO_RUN_RESULT = "## Auto Run Result"


def contracted(**over: Any) -> dict[str, Any]:
    """The `with_resolved` of a *planned* `agent` row: `expect` and `retry` included."""
    extras: dict[str, Any] = {
        EXPECT_KEY: {
            "files": [STORY_GLOB],
            "status_in": ["done", "blocked", "ready-for-dev"],
        },
        RETRY_KEY: {"max": RETRY_MAX, "prompt": RETRY_PROMPT, "resume_session": True},
    }
    extras.update(over)
    return resolved(**extras)


def a_story(status: str = "done", condition: str | None = None, tail: str = "") -> str:
    """A Story file as `bmad-build-auto`'s HALT protocol writes one."""
    lines = [
        "---",
        f"status: {status}",
        "title: notify",
        "---",
        "",
        "# Story 4-1",
        "",
        AUTO_RUN_RESULT,
        "",
        f"Status: {status}",
    ]
    if condition is not None:
        lines.append(f"Blocking condition: {condition}")
    if tail:
        lines.extend(["", tail])
    return "\n".join([*lines, ""])


def a_section(status: str = "done", condition: str | None = None) -> str:
    """The whole `## Auto Run Result` section of `a_story`, as `route` reads it back."""
    lines = [AUTO_RUN_RESULT, "", f"Status: {status}"]
    if condition is not None:
        lines.append(f"Blocking condition: {condition}")
    return "\n".join(lines)


DONE_STORY = a_story()


def a_tail_world(  # noqa: PLR0913 — one keyword per fact of the tail, each optional
    *,
    story: str | None = DONE_STORY,
    files: dict[str, str] | None = None,
    with_resolved: dict[str, Any] | None = None,
    exit_code: int | None = 0,
    harness: FakeHarness | None = None,
    git: FakeGit | None = None,
    mtimes: dict[str, float] | None = None,
    **over: Any,
) -> World:
    """An `agent` row that dispatches, exits with `exit_code`, and leaves `story` behind."""
    the_harness = harness if harness is not None else FakeHarness()
    the_harness.results.append(
        HarnessResult(session_id=SESSION_ID, exit_code=exit_code, log_path=LOG_PATH)
    )
    tree = dict(files or {})
    if story is not None:
        tree[STORY_PATH] = story
    world = a_world(
        with_resolved=with_resolved if with_resolved is not None else contracted(),
        files=tree,
        git=git if git is not None else FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]),
        harness=the_harness,
        **over,
    )
    world.workspace.mtimes.update(mtimes or {})
    return world


def retried(world: World, count: int) -> StepContext:
    """The same row, with the retry counter where `apply_step_result` would have left it."""
    return replace(world.ctx, row=world.row.model_copy(update={"retry_count": count}))


def redispatched(world: World, count: int = 1) -> StepContext:
    """The same row, re-queued by a `verify` row that failed (AD-9's bounded route back)."""
    return replace(world.ctx, row=world.row.model_copy(update={"redispatch_count": count}))
