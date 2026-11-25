"""A Run parked `merge_conflict` on a `git.merge` row, for story 8.4's tests (shared fakes)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.writer_fixtures import World, a_world, an_attempt

MERGE = "epics[0].merge"
AGENT = "epics[0].merge-agent"
SKILL = "bmad-merge-resolver"
PLAN = (
    ("plan", "plan.check"),
    ("epics[0].checkout", "git.worktree"),
    (AGENT, "agent"),
    (MERGE, "git.merge"),
    ("epics[0].push", "git.push"),
)
REASON = "merge conflict: feat/epic-1 into develop"
PARK = Park(kind="merge_conflict", reason=REASON, path=MERGE)


def parked_result() -> StepResult:
    return StepResult(status="error", gate="deterministic", reason=REASON, park=PARK)


def a_merge_world(*, initiative: bool = True, skill: str | None = SKILL) -> World:
    agent: dict[str, Any] = {"skill": skill} if skill else {}
    world = a_world(
        "running",
        PLAN,
        {MERGE: "running", AGENT: "done"},
        {AGENT: agent},
        inputs={"harness": "claude", "model": "claude-sonnet"},
        **(
            {"initiative_id": new_id(), "initiative_round": 1, "initiative_position": 1}
            if initiative
            else {}
        ),
    )
    world.ports = replace(world.ports, engine=world.engine)
    an_attempt(world, MERGE)
    return world


def a_parked_merge_world(**over: Any) -> World:
    world = a_merge_world(**over)
    apply_step_result(world.ports, world.run.id, world.row(MERGE).seq, parked_result())
    return world
