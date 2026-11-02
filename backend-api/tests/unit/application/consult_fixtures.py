"""Worlds for story 1-4's consult tests (spine AD-22), built on the shared `agent` worlds.

Nothing new is faked: the row, the ports and the recorders are `agent_fixtures.py`'s and
`agent_tail_fixtures.py`'s. What is added is the planned `consult` block a fixture row
carries, and a world standing on a `consult` attempt whose entry the offer left `due`.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.harness import HarnessResult, HarnessUsage
from tests.unit.application.steps.agent_fixtures import (
    WORKTREE,
    World,
    a_world,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    a_section,
    a_story,
    a_tail_world,
    contracted,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness

SENIOR_MODEL = "senior-model"
CONSULT_SKILL = "senior-consult"
DISPATCH = (
    "Run {skill} for story {story_id} in {spec_folder}. The agent asks: {condition}. "
    "Write {decision}."
)
ANSWER = 'Answer from the senior reviewer to the blocking condition "{condition}": {answer}'
CONDITION = "intent gap"
QUESTION = a_section("blocked", CONDITION)
AGENT_SESSION = "s-agent"
AGENT_END = "e" * 40
SNAP_HEAD = "5" * 40
CONSULT_LOG = Path("/work/logs/003-2.log")
DECISION = ".orchestrator/consult/003-2.decision.md"


def planned(**over: Any) -> dict[str, Any]:
    """The `consult` block the planner writes on a row (`templates/agent_row.py`)."""
    block: dict[str, Any] = {
        "model": SENIOR_MODEL,
        "harness": "",
        "skill": CONSULT_SKILL,
        "on": ["blocked"],
        "timeout_min": 20,
        "prompts": {"dispatch": DISPATCH, "answer": ANSWER},
    }
    block.update(over)
    return block


def consulting(**over: Any) -> dict[str, Any]:
    """A planned agent row with the story contract and a consult on `blocked`."""
    return contracted(**{"consult": planned(), **over})


def a_blocking_world(**over: Any) -> World:
    """The agent's own dispatch, which blocks on `CONDITION` and reports a session."""
    fields: dict[str, Any] = {
        "story": a_story("blocked", CONDITION),
        "with_resolved": consulting(),
    }
    fields.update(over)
    return a_tail_world(**fields)


def with_consults(world: World, consults: dict[str, Any]) -> World:
    row = world.row.model_copy(update={"consults": consults})
    return replace(world, row=row, ctx=replace(world.ctx, row=row))


def a_decision(status: str = "answer", body: str = "Use the v2 route.", reason: str = "") -> str:
    head = f"---\nstatus: {status}\n" + (f"reason: {reason}\n" if reason else "") + "---\n"
    return f"{head}\n{body}\n"


def due_entry(**over: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "state": "due",
        "question": QUESTION,
        "snapshot": {"tree": {"head": SNAP_HEAD, "status": ""}},
    }
    entry.update(over)
    return entry


def a_consult_world(  # noqa: PLR0913 — one keyword per fact of the consult, each optional
    *,
    decision: str | None = None,
    result: HarnessResult | None = None,
    git: FakeGit | None = None,
    entry: dict[str, Any] | None = None,
    with_resolved: dict[str, Any] | None = None,
    harnesses: dict[str, Any] | None = None,
    **over: Any,
) -> World:
    """Attempt 2, a `consult`, on a row whose agent attempt 1 blocked and was offered."""
    harness = FakeHarness()
    harness.results.append(
        result
        if result is not None
        else HarnessResult(
            session_id="s-senior",
            exit_code=0,
            log_path=CONSULT_LOG,
            usage=HarnessUsage(tokens_in=10, tokens_out=5, cost_usd=None),
        )
    )
    files = {DECISION: decision} if decision is not None else {}
    resolved = with_resolved if with_resolved is not None else consulting()
    probe = a_world(with_resolved=resolved)
    previous = an_attempt(
        probe.row,
        1,
        status="error",
        session_id=AGENT_SESSION,
        start_sha="1" * 40,
        end_sha=AGENT_END,
        harness="claude",
    )
    world = a_world(
        with_resolved=resolved,
        files=files,
        harness=harness,
        harnesses=harnesses,
        previous=previous,
        git=git
        if git is not None
        else FakeGit(heads={WORKTREE: [SNAP_HEAD]}, statuses={WORKTREE: ""}),
        **over,
    )
    consult_attempt = world.attempt.model_copy(update={"role": "consult"})
    world.attempts.attempts[consult_attempt.id] = consult_attempt
    row = world.row.model_copy(
        update={"consults": {"blocked": entry if entry is not None else due_entry()}}
    )
    ctx = replace(world.ctx, row=row, attempt=consult_attempt)
    return replace(world, ctx=ctx, row=row, attempt=consult_attempt)
