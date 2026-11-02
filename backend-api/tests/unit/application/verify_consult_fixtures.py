"""Worlds for story 1-6's `verify_failed` consult tests (spine AD-22), on the writers' world.

The verify row (`stories[0].verify`, `shell`) declares a planned `on_fail` redispatch to
`stories[0].build` (`agent`) with a consult; the build row is `done`, its redispatch counter
at the bound. Nothing new is faked: the git double is `FakeGit`."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.domain.values import Consult, Redispatch, StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
WORKTREE = "/work/p/r/wt/initiative"
MAX = 2
QUESTION = "verify failed 3/3"
HEAD = "a" * 40
ANSWER = 'Diagnosis of "{condition}": {answer}'
BLOCK: dict[str, Any] = {
    "model": "senior",
    "harness": "",
    "skill": "senior-consult",
    "on": ["verify_failed"],
    "timeout_min": None,
    "prompts": {"dispatch": "d {command} {code} {tail} {log} {decision}", "answer": ANSWER},
}


def clean_git(**over: Any) -> FakeGit:
    fields: dict[str, Any] = {"heads": {WORKTREE: [HEAD]}, "statuses": {WORKTREE: ""}}
    fields.update(over)
    return FakeGit(**fields)


def a_verify_world(  # noqa: PLR0913 — one keyword per fact of the world, each optional
    *,
    count: int = MAX,
    block: dict[str, Any] | None = BLOCK,
    consults: dict[str, Any] | None = None,
    git: FakeGit | None = None,
    build: str = "done",
    workdir: str | None = None,
    worktree: str | None = WORKTREE,
) -> World:
    """A running Run whose verify row is about to report a failure; the build row is `build`,
    its redispatch counter at `count`."""
    route: dict[str, Any] = {"target_seq": 5, "max": MAX}
    if block is not None:
        route["consult"] = block
    resolved = {
        BUILD: {"story_id": "1", "harness": "claude", **({"workdir": workdir} if workdir else {})},
        VERIFY: {"command": "make test", "on_fail": route},
    }
    world = a_world(
        "running",
        EPIC_PLAN,
        {BUILD: build, VERIFY: "running"},  # type: ignore[dict-item]
        resolved,
        worktree_path=worktree,
    )
    world.ports = replace(world.ports, git=git if git is not None else clean_git())
    updates: dict[str, Any] = {"redispatch_count": count}
    if consults is not None:
        updates["consults"] = consults
    world.ports.steps.update(world.row(BUILD).model_copy(update=updates))
    return world


def a_failed_verify() -> StepResult:
    return StepResult(
        status="error",
        gate="deterministic",
        reason="exit 2",
        redispatch=Redispatch(target_seq=5, max=MAX),
    )


def an_answer(text: str = "The mock is stale.") -> StepResult:
    return StepResult(
        status="error",
        gate="liveness",
        reason="senior answered: The mock is stale.",
        consult=Consult(kind="verify_failed", question=QUESTION, outcome="answer", answer=text),
    )
