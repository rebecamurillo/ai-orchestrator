"""`sweep_session_turns`: the start-up half of a turn lost before its enqueue (story 2-5,
AD-6, AD-23). Every `queued` session attempt is enqueued again while its Run still holds the
session, and closed `error` `session closed` otherwise. Nothing else is touched."""

from __future__ import annotations

from orchestrator.application.use_cases.session_sweep import sweep_session_turns
from orchestrator.application.use_cases.session_turn import SESSION_CLOSED
from tests.unit.application.session_fixtures import BUILD
from tests.unit.application.session_turn_fixtures import a_turn_world


def test_a_queued_turn_whose_session_is_open_is_enqueued_again() -> None:
    world = a_turn_world()
    queued = world.session.turn(1, status="queued", ended_at=None)
    world.session.turn(2, status="running", ended_at=None)
    world.session.turn(3, status="done")
    engine = world.session.world.engine
    calls = len(engine.calls)

    sweep_session_turns(world.writers, engine)

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

    sweep_session_turns(world.writers, engine)

    assert engine.calls[calls:] == []
    stored = world.attempt(queued.id)
    assert (stored.status, stored.output_ref) == ("error", SESSION_CLOSED)
    assert stored.ended_at == world.session.world.clock.now()


def test_an_agent_attempt_is_never_swept() -> None:
    world = a_turn_world()
    agent = world.session.turn(1, role="agent", status="queued", ended_at=None)
    engine = world.session.world.engine
    calls = len(engine.calls)

    sweep_session_turns(world.writers, engine)

    assert engine.calls[calls:] == []
    assert world.session.world.attempts_of(BUILD) == [agent]
