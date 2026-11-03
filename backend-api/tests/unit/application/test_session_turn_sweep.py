"""`sweep_session_turns`: the start-up half of a turn a crash lost (story 2-5, AD-6, AD-23).

Every `queued` session attempt is enqueued again while its Run still holds the session, and
closed `error` `session closed` otherwise. An open turn past `queued` that the engine no
longer holds (its workflow ended in error, so nothing recovers it) is interrupted when it
was running, then committed, closed and billed, so the session can take a message or end
again (story 2-5 review, 2026-11-02)."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from orchestrator.application.rules.session import TURN_MESSAGE
from orchestrator.application.use_cases.session_sweep import sweep_session_turns
from orchestrator.application.use_cases.session_turn import INTERRUPTED, SESSION_CLOSED
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.gateway import AttemptSpend
from tests.unit.application.session_fixtures import BUILD, WORKTREE
from tests.unit.application.session_turn_fixtures import a_turn_world
from tests.unit.fakes.git import FakeGit

COST = Decimal("0.200000")


def test_a_queued_turn_whose_session_is_open_is_enqueued_again() -> None:
    world = a_turn_world()
    queued = world.session.turn(1, status="queued", ended_at=None)
    running = world.session.turn(2, status="running", ended_at=None, pgid=5)
    world.session.turn(3, status="done")
    engine = world.session.world.engine
    calls = len(engine.calls)

    sweep_session_turns(world.ports, engine, held={running.id})

    assert engine.calls[calls:] == [
        ("enqueue_session_turn", (world.session.world.run.id, queued.id))
    ]
    assert world.attempt(queued.id) == queued


def test_a_queued_turn_whose_session_closed_is_closed_and_not_enqueued() -> None:
    world = a_turn_world()
    queued = world.session.turn(1, status="queued", ended_at=None)
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(
        run.model_copy(update={"status": "cancelled", "senior_session": False})
    )
    engine = world.session.world.engine
    calls = len(engine.calls)

    sweep_session_turns(world.ports, engine)

    assert engine.calls[calls:] == []
    stored = world.attempt(queued.id)
    assert (stored.status, stored.output_ref) == ("error", SESSION_CLOSED)
    assert stored.ended_at == world.session.world.clock.now()


def test_an_agent_attempt_is_never_swept() -> None:
    world = a_turn_world()
    agent = world.session.turn(1, role="agent", status="queued", ended_at=None)
    engine = world.session.world.engine
    calls = len(engine.calls)

    sweep_session_turns(world.ports, engine)

    assert engine.calls[calls:] == []
    assert world.session.world.attempts_of(BUILD) == [agent]


def test_a_running_turn_the_engine_no_longer_holds_is_recovered_and_the_session_freed() -> None:
    git = FakeGit(status=[" M src/app.py"])
    world = a_turn_world(git=git)
    stuck = world.session.turn(1, status="running", ended_at=None, pgid=917, start_sha="a" * 40)
    world.gateway.script(
        world.session.world.run.id,
        stuck.id,
        AttemptSpend(usd=COST, tokens_in=1, tokens_out=1, by_model=(), calls=1, provisional=False),
    )

    sweep_session_turns(world.ports, world.session.world.engine, held=set())

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 917}]
    assert git.called("commit") == [(Path(WORKTREE), TURN_MESSAGE.format(k=1))]
    stored = world.attempt(stuck.id)
    assert (stored.status, stored.output_ref) == ("error", INTERRUPTED)
    assert stored.ended_at is not None
    assert world.session.world.stored_run().spend_usd == COST
    assert world.post("Again?").status == "queued"


def test_a_finished_turn_left_open_is_committed_and_closed_keeping_its_status() -> None:
    world = a_turn_world()
    stuck = world.session.turn(1, status="done", ended_at=None, exit_code=0, pgid=4)

    sweep_session_turns(world.ports, world.session.world.engine)

    stored = world.attempt(stuck.id)
    assert (stored.status, stored.ended_at is not None) == ("done", True)
    assert world.process.called("kill_group") == []
    world.session.send("session_end")
    assert world.session.world.stored_run().senior_session is False


def test_a_recovery_that_fails_is_logged_and_the_sweep_goes_on() -> None:
    world = a_turn_world()
    stray = world.session.turn(1, status="done", ended_at=None, step_run_id=new_id())
    queued = world.session.turn(2, status="queued", ended_at=None)
    engine = world.session.world.engine

    sweep_session_turns(world.ports, engine)

    assert world.attempt(stray.id).ended_at is None
    assert engine.calls[-1] == ("enqueue_session_turn", (world.session.world.run.id, queued.id))
