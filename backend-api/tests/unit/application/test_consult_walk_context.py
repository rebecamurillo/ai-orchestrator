"""`walk_context.context` and the senior's answer (story 1-4, spine AD-9/AD-22, 2026-11-02).

The answer travels as a real `senior_answer` record, resolved as `resume_signal` when no
Operator signal resumed the row, so the agent executor's session path needs no change."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.walk import WalkPorts, run_row
from orchestrator.application.use_cases.walk_context import redispatches_to
from orchestrator.application.use_cases.writers import Entry, record
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

BUILD = "stories[0].build"
ANSWERED = {"blocked": {"state": "answer", "question": "q", "answered_by": 2}}


class Recording:
    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("agent", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def an_answered_world() -> World:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    world.ports.steps.update(world.row(BUILD).model_copy(update={"consults": ANSWERED}))
    an_attempt(world, BUILD, n=1, status="error", session_id="s1", end_sha="a" * 40)
    an_attempt(world, BUILD, n=2, role="consult", status="error", session_id="s2")
    an_attempt(world, BUILD, n=3)
    return world


def ports(world: World) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
    )


def senior_answer(world: World) -> None:
    record(
        world.ports,
        world.run,
        Entry(
            event="senior_answer",
            actor="senior",
            path=BUILD,
            attempt_n=2,
            payload={"mode": "session", "text": "Do X.", "kind": "blocked"},
        ),
    )


def test_the_senior_answer_is_the_resume_signal_of_the_next_agent_attempt(
    executor: Recording,
) -> None:
    world = an_answered_world()
    senior_answer(world)

    run_row(ports(world), world.run.id, world.row(BUILD).seq)

    [ctx] = executor.seen
    assert ctx.resume_signal is not None
    assert ctx.resume_signal.event == "senior_answer"
    assert ctx.resume_signal.payload["mode"] == "session"
    assert ctx.previous_attempt is not None
    assert (ctx.previous_attempt.n, ctx.previous_attempt.session_id) == (1, "s1")
    assert (ctx.attempt.n, ctx.attempt.role) == (3, "agent")


def test_an_operator_signal_wins_over_the_senior_answer(executor: Recording) -> None:
    world = an_answered_world()
    senior_answer(world)
    record(world.ports, world.run, Entry(event="answer", actor="operator", path=BUILD))

    run_row(ports(world), world.run.id, world.row(BUILD).seq, "answer")

    [ctx] = executor.seen
    assert ctx.resume_signal is not None
    assert ctx.resume_signal.event == "answer"


def test_a_row_with_no_answer_has_no_resume_signal(executor: Recording) -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    an_attempt(world, BUILD, n=1)

    run_row(ports(world), world.run.id, world.row(BUILD).seq)

    [ctx] = executor.seen
    assert ctx.resume_signal is None


def test_a_redispatch_is_matched_on_the_target_seq() -> None:
    world = a_world("running", EPIC_PLAN, with_resolved={BUILD: {"on_fail": {"target_seq": 3}}})

    assert redispatches_to(world.row(BUILD), 3)
    assert not redispatches_to(world.row(BUILD), 4)
    assert not redispatches_to(world.row("stories[0].verify"), 3)
