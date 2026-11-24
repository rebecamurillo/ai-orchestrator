"""The resumed execute routes the step file (epic 5 story 3, 2026-11-24; AD-38 "Resumed execute").

Fixture rows and fixture step files the tests own; no shipped template.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.steps import StepContext
from orchestrator.application.steps.conversation import ConversationExecutor
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.test_conversation_close_check import (
    TREE,
    a_closing_world,
    a_git,
    context_of,
)
from tests.unit.application.writer_fixtures import World
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.workspace import FakeWorkspace

EXPECT = {"files": ["PRD.md"], "success": ["final"], "blocked": ["blocked"]}
NO_HIT = FakeGit(heads={TREE: ["h1"]}, changes={TREE: ()}, statuses={TREE: ""})
STAYS = "the step stays open"


def sentence(what: str, done: str = "final") -> str:
    return f"step not closed · PRD.md {what}, the done content is status {done} · {STAYS}"


def resume(
    world: World,
    event: str,
    files: dict[str, str] | None,
    git: FakeGit | None = None,
) -> tuple[StepResult, list[str | None]]:
    roots: list[str | None] = []

    def workspace(root: str | None) -> FakeWorkspace:
        roots.append(root)
        return FakeWorkspace(root=TREE, files=files or {})

    ctx = context_of(world, event, git or NO_HIT)
    ctx = _with(ctx, workspace if files is not None else None)
    return ConversationExecutor().execute(ctx), roots


def _with(ctx: StepContext, workspace: Any) -> StepContext:
    ports = ctx.ports.__class__(**{**ctx.ports.__dict__, "workspace": workspace})
    return ctx.__class__(**{**ctx.__dict__, "ports": ports})


def applied(world: World, result: StepResult) -> None:
    apply_step_result(world.ports, world.run.id, world.row("tech").seq, result)


def test_ac1_a_done_word_ends_the_row_and_queues_the_next() -> None:
    world = a_closing_world(expect=EXPECT)

    result, roots = resume(world, "step_close", {"PRD.md": "---\nstatus: final\n---\n"})

    assert (result.status, result.park) == ("done", None)
    assert roots == [TREE]
    applied(world, result)
    assert world.status_of("tech") == "done"
    assert world.status_of("after") == "queued"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("---\nstatus: draft\n---\n", sentence("has status draft")),
        ("---\nstatus: blocked\n---\n", sentence("has status blocked")),
    ],
)
def test_ac2_ac3_another_status_re_parks_the_conversation(text: str, reason: str) -> None:
    world = a_closing_world(expect=EXPECT)
    before = len(world.attempts_of("tech"))

    result, _ = resume(world, "step_close", {"PRD.md": text})

    assert result.status == "checkpoint"
    assert result.reason == reason
    assert result.park is not None
    assert (result.park.kind, result.park.path, result.park.reason) == (
        "conversation",
        "tech",
        reason,
    )
    applied(world, result)
    run = world.stored_run()
    assert (run.status, run.park_kind, run.senior_session) == ("needs_you", "conversation", True)
    assert len(world.attempts_of("tech")) == before
    assert sum(1 for a in world.attempts_of("tech") if a.role == "session") == 1


def test_ac4_a_missing_file_is_named_missing() -> None:
    world = a_closing_world(expect=EXPECT)

    result, _ = resume(world, "step_close", {})

    assert result.park is not None
    assert result.park.reason == sentence("is missing")


@pytest.mark.parametrize(
    "text", ["# no frontmatter\n", "---\nstatus: 3\n---\n", "---\nstatus: [a]\n---\n"]
)
def test_ac5_an_unreadable_status_is_no_status(text: str) -> None:
    world = a_closing_world(expect={**EXPECT, "success": ["final", "accepted"]})

    result, _ = resume(world, "step_close", {"PRD.md": text})

    assert result.park is not None
    assert result.park.reason == sentence("has no status", "final or accepted")


def test_ac6_an_anchor_hit_parks_before_the_file_is_read() -> None:
    world = a_closing_world(expect=EXPECT)

    result, _ = resume(world, "step_close", None, a_git())

    assert result.park is not None
    assert result.park.kind == "protected_path"


@pytest.mark.parametrize(
    ("text", "status"),
    [("---\nstatus: final\n---\n", "done"), ("---\nstatus: draft\n---\n", "checkpoint")],
)
def test_ac7_the_continue_routes_the_step_file_the_same_way(text: str, status: str) -> None:
    world = a_closing_world(expect=EXPECT, accepted=("backend-api/AGENTS.md",))

    result, _ = resume(world, "continue", {"PRD.md": text}, a_git())

    assert result.status == status
    if status == "checkpoint":
        assert result.reason == sentence("has status draft")


@pytest.mark.parametrize("expect", ["not a mapping", {"success": ["final"]}, {"files": []}])
def test_no_declared_file_reads_as_missing_with_an_empty_name(expect: Any) -> None:
    world = a_closing_world(expect=expect)

    result, roots = resume(world, "step_close", {})

    assert result.park is not None
    assert result.park.reason == (
        f"step not closed ·  is missing, the done content is status "
        f"{'final' if isinstance(expect, dict) and expect.get('success') else ''} · {STAYS}"
    )
    assert roots == []
