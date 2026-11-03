"""A senior's answer is delivered the way an Operator's answer is (story 1-4 review, spine
AD-13/AD-22, 2026-11-02): the stopped marker is archived with the answer appended under a
senior heading, and a fresh redispatch carries the consult's own answer clause. A session
delivery still sends the consult's clause, never the row's operator one."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_prompt import compose_prompt
from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.application.use_cases.walk import apply_result, attempt_row, next_row
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.ports.harness import HarnessResult
from tests.unit.application.consult_fixtures import consulting, planned
from tests.unit.application.steps.agent_fixtures import (
    HALT_CLAUSE,
    STORY_ID,
    World,
    a_gate_record,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    ANSWERS,
    DONE_STORY,
    a_story,
    a_tail_world,
)
from tests.unit.application.test_walk_consult_loop import (
    AGENT_SESSION,
    BUILD,
    LOG,
    MARKER,
    SENIOR_ANSWER,
    SPEC_FOLDER,
    Loop,
    script,
)
from tests.unit.application.test_walk_consult_loop import STORY_ID as LOOP_STORY_ID

TEXT = 'Answer from the senior reviewer to the blocking condition "q": Use v2.'
ARCHIVED = f"{ANSWERS}/{STORY_ID}-attempt-1.md"
LOOP_ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/{LOOP_STORY_ID}-attempt-1.md"
SENIOR_HEADING = "## Senior Answer"


def a_senior_answer(world: World) -> GateRecord:
    record = a_gate_record(
        world.row, "senior_answer", {"mode": "session", "text": TEXT, "kind": "blocked"}
    )
    return record.model_copy(update={"actor": "senior"})


def a_resumed_world(**over: Any) -> World:
    """Attempt 2 of a row whose agent attempt 1 blocked and whose senior answered."""
    probe = a_tail_world()
    previous = an_attempt(
        probe.row,
        1,
        status="error",
        session_id=AGENT_SESSION,
        start_sha="1" * 40,
        end_sha="2" * 40,
    )
    world = a_tail_world(
        story=a_story("blocked", "q"), with_resolved=consulting(**over), previous=previous
    )
    return replace(world, ctx=replace(world.ctx, resume_signal=a_senior_answer(world)))


# ── the archive ──────────────────────────────────────────────────────────────


def test_a_senior_answer_archives_the_stopped_marker_under_a_senior_heading() -> None:
    world = a_resumed_world()

    AgentExecutor().execute(world.ctx)

    archived = world.workspace.read(ARCHIVED)
    assert archived is not None
    assert SENIOR_HEADING in archived
    assert "· senior" in archived
    assert TEXT in archived
    assert "## Human Answer" not in archived


def test_the_session_is_sent_the_consults_clause_not_the_operators() -> None:
    world = a_resumed_world()

    AgentExecutor().execute(world.ctx)

    [resumed] = world.harness.called("resume")
    assert resumed["message"] == TEXT


# ── a fresh dispatch ─────────────────────────────────────────────────────────


def test_a_fresh_dispatch_after_a_senior_answer_carries_its_clause() -> None:
    world = a_resumed_world()

    prompt = compose_prompt(world.ctx.with_resolved, a_senior_answer(world), None)

    assert prompt.endswith(TEXT)


def test_a_fresh_plan_dispatch_after_a_senior_answer_halts_again() -> None:
    world = a_resumed_world(spec_checkpoint=True)

    prompt = compose_prompt(world.ctx.with_resolved, a_senior_answer(world), None)

    assert prompt.endswith(f"{TEXT} {HALT_CLAUSE}")


# ── in the walker's loop ─────────────────────────────────────────────────────


def test_a_resumed_agent_that_leaves_the_marker_does_not_repark_on_the_old_question() -> None:
    """The archive empties the glob, so the stop is FR-16's `no story file`, the same stop an
    Operator's answer reaches today (never auto-retried, Operator decision 2026-09-20) —
    not the senior's question again with its consult used up."""
    loop = Loop(consult=planned())
    script(loop)
    loop.harness.on_resume = None

    statuses = [loop.turn(), loop.turn(), loop.turn()]

    assert statuses == ["running", "running", "needs_you"]
    assert loop.world.events() == ["consult", "senior_answer", "misconfigured"]
    assert loop.world.stored_run().park_reason == "no story file"
    assert loop.workspace.read(MARKER) is None
    assert SENIOR_HEADING in (loop.workspace.read(LOOP_ARCHIVED) or "")


def test_an_answer_survives_a_crash_of_the_resumed_attempt() -> None:
    loop = Loop(consult=planned())
    script(loop)
    loop.turn()
    loop.turn()
    seq = next_row(loop.ports(), loop.world.run.id)
    assert seq is not None
    # the resumed attempt opens and the backend dies before it reports back
    start_attempt(loop.ports().writers, loop.world.run.id, seq)
    loop.harness.results.insert(0, HarnessResult(session_id="s-new", exit_code=0, log_path=LOG))
    loop.harness.on_wait = lambda: loop.workspace.write(MARKER, DONE_STORY)

    result = attempt_row(loop.ports(), loop.world.run.id, seq, {})

    assert apply_result(loop.ports(), loop.world.run.id, seq, result) == "done"
    fresh = loop.harness.called("start")[-1]
    assert fresh["session_id"] != AGENT_SESSION
    assert "Answer from the senior reviewer" in fresh["prompt"]
    assert fresh["prompt"].endswith(SENIOR_ANSWER)
    roles = [(attempt.n, attempt.role) for attempt in loop.world.attempts_of(BUILD)]
    assert roles[-2:] == [(3, "agent"), (4, "agent")]
