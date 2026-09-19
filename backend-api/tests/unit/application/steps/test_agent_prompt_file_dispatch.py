"""`AgentExecutor.execute()` with a `prompt_file` in `with_resolved`.

Covers the new `_planned()` branch that reads a file from the workspace and passes its
content to `compose_prompt` — 100% application branch coverage for the new path.
"""

from __future__ import annotations

from orchestrator.application.steps.agent import AgentExecutor
from tests.unit.application.steps.agent_fixtures import (
    a_world,
    resolved,
)
from tests.unit.fakes.git import FakeGit

PLAN_FILE = "plan.md"
PLAN_CONTENT = "Implement the widget feature as described."

HEAD_SHA = "aabbccdd" * 5
END_SHA = "11223344" * 5


def _resolved_prompt_file(**over: object) -> dict[str, object]:
    """A `with_resolved` using `prompt_file` instead of `skill`."""
    row = resolved()
    del row["skill"]
    row["prompt_file"] = PLAN_FILE
    row.update(over)  # type: ignore[arg-type]
    return row


def test_workspace_read_is_called_with_the_declared_filename() -> None:
    """The executor reads exactly the filename named in `prompt_file`."""
    world = a_world(
        with_resolved=_resolved_prompt_file(),
        files={PLAN_FILE: PLAN_CONTENT},
        git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]),
    )

    AgentExecutor().execute(world.ctx)

    assert world.workspace.read(PLAN_FILE) == PLAN_CONTENT


def test_file_content_reaches_the_harness_as_the_prompt() -> None:
    """The content read from the file becomes the prompt base the harness receives."""
    world = a_world(
        with_resolved=_resolved_prompt_file(),
        files={PLAN_FILE: PLAN_CONTENT},
        git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]),
    )

    AgentExecutor().execute(world.ctx)

    start_calls = world.harness.called("start")
    assert start_calls, "harness.start was never called"
    prompt = start_calls[0]["prompt"]
    assert PLAN_CONTENT in prompt


def test_absent_file_gives_empty_prompt_base() -> None:
    """When the named file does not exist, `ws.read()` returns None → base is `""`."""
    world = a_world(
        with_resolved=_resolved_prompt_file(),
        files={},  # file not present
        git=FakeGit(status=[""], head_sha=[HEAD_SHA, END_SHA]),
    )

    AgentExecutor().execute(world.ctx)

    start_calls = world.harness.called("start")
    assert start_calls
    prompt = start_calls[0]["prompt"]
    # DISPATCH sentence must NOT appear — base is "" from the prompt_file branch
    assert "Run the skill" not in prompt
