"""A senior session's turns end to end over the shared fakes (story 2-5, AD-21, AD-23):
two turns share one harness session, the agent's own session survives the session, a hub
turn commits each tree, a cancel mid-turn keeps the Run cancelled and billed, and a turn a
crash left open is recovered so `session_end` works again."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.rules.session import TURN_MESSAGE
from orchestrator.application.use_cases.session_turn import INTERRUPTED, post_message
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.start_attempt import start_attempt
from orchestrator.application.use_cases.walk_context import context
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from orchestrator.domain.values import Signal
from tests.unit.application.session_fixtures import BUILD, WORKTREE
from tests.unit.application.session_turn_fixtures import ROW, TurnWorld, a_result, a_turn_world
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.git import FakeGit

AGENT_SESSION = "s-agent"
COST = Decimal("0.300000")


def with_agent_attempt(world: TurnWorld) -> None:
    row = world.session.world.row(BUILD)
    world.session.turn(
        1, role="agent", status="blocked", session_id=AGENT_SESSION, started_at=EPOCH
    )
    assert world.session.world.attempts_of(BUILD)[0].step_run_id == row.id


def test_the_second_turn_resumes_the_first_turns_session() -> None:
    world = a_turn_world(results=[a_result(session_id="s-senior"), a_result(session_id="s-senior")])

    first = world.turn("Why is the route missing?")
    second = world.turn("And the v1 route?")

    assert first.session_id == "s-senior"
    (resumed,) = world.harness.called("start_resume")
    assert (resumed["session_id"], resumed["message"]) == ("s-senior", "And the v1 route?")
    assert second.ended_at is not None


def test_an_answer_after_the_session_resumes_the_agents_own_session() -> None:
    world = a_turn_world(start=False)
    with_agent_attempt(world)
    world.session.world.clock.advance(1)
    world.session.start()
    world.turn()
    world.turn("One more question.")
    world.session.send("session_end")
    writers = world.writers
    ports = SignalPorts(
        writers=writers,
        engine=world.session.world.engine,
        harness_is_resumable=lambda _name: True,
        latest_attempt_for_run=writers.attempts.latest_for_run,
    )

    signal_run(ports, world.session.world.run.id, Signal(kind="answer", payload={"text": "go"}))
    seq = world.session.world.row(BUILD).seq
    start_attempt(writers, world.session.world.run.id, seq)
    run = world.session.world.stored_run()
    ctx = context(writers, world.step, run, seq, "answer")

    assert ctx.attempt.role == "agent"
    assert ctx.previous_attempt is not None
    assert ctx.previous_attempt.session_id == AGENT_SESSION
    assert ctx.resume_signal is not None
    assert ctx.resume_signal.payload["mode"] == "session"


def test_a_hub_turn_editing_both_trees_commits_turn_1_in_each() -> None:
    member = f"{WORKTREE}/repos/m"
    git = FakeGit(statuses={member: "", WORKTREE: ""})
    world = a_turn_world(git=git, with_resolved={**ROW, "workdir": "repos/m"})

    def edits_both() -> None:
        assert git.statuses is not None
        git.statuses[member] = " M src/x.py"
        git.statuses[WORKTREE] = " M specs/demo/notes.md"

    world.harness.on_wait = edits_both

    world.turn()

    message = TURN_MESSAGE.format(k=1)
    assert git.called("commit") == [
        (Path(WORKTREE), message, "repos/m"),
        (Path(WORKTREE), message),
    ]


def test_a_cancel_mid_turn_kills_the_group_and_the_run_stays_cancelled_and_billed() -> None:
    world = a_turn_world(results=[a_result(), a_result(exit_code=None)])
    world.turn()
    posted = world.post("Second question.")
    plans: list[object] = []

    def cancelled() -> None:
        plans.append(world.session.send("cancel").cancel_plan)
        world.gateway.script(
            world.session.world.run.id,
            posted.attempt_id,
            AttemptSpend(
                usd=COST, tokens_in=1, tokens_out=1, by_model=(), calls=1, provisional=False
            ),
        )

    world.harness.on_wait = cancelled
    commits = len(world.git.called("commit"))

    world.run(posted.attempt_id)
    world.commit(posted.attempt_id)

    (plan,) = plans
    assert world.harness.pgid in plan.pgids  # type: ignore[attr-defined]
    assert len(world.git.called("commit")) == commits
    turn = world.attempt(posted.attempt_id)
    assert (turn.status, turn.cost_usd) == ("error", COST)
    assert turn.ended_at is not None
    run = world.session.world.stored_run()
    assert (run.status, run.senior_session) == ("cancelled", False)
    assert run.spend_usd == COST


def test_a_message_queued_before_a_cancel_is_closed_and_never_dispatched() -> None:
    world = a_turn_world()
    posted = world.post()
    world.session.send("cancel")

    world.run(posted.attempt_id)
    world.commit(posted.attempt_id)

    assert world.harness.calls == []
    turn = world.attempt(posted.attempt_id)
    assert (turn.status, turn.output_ref) == ("error", "session closed")
    assert turn.ended_at is not None


def test_a_turn_a_crash_left_running_is_recovered_and_session_end_works_again() -> None:
    world = a_turn_world()
    crashed = world.session.turn(
        1, status="running", ended_at=None, pgid=917, session_id="s-1", start_sha="a" * 40
    )
    with pytest.raises(Conflict, match=TURN_RUNNING):
        world.session.send("session_end")
    world.gateway.script(
        world.session.world.run.id,
        crashed.id,
        AttemptSpend(usd=COST, tokens_in=1, tokens_out=1, by_model=(), calls=1, provisional=False),
    )

    world.run(crashed.id)
    world.commit(crashed.id)

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 917}]
    assert world.harness.calls == []
    turn = world.attempt(crashed.id)
    assert (turn.status, turn.output_ref) == ("error", INTERRUPTED)
    assert turn.ended_at is not None
    assert world.session.world.stored_run().spend_usd == COST
    world.session.send("session_end")
    assert world.session.world.stored_run().senior_session is False


def test_an_unknown_run_refuses_a_message() -> None:
    world = a_turn_world()

    with pytest.raises(NotFound):
        post_message(world.messages, new_id(), "go")
