"""`retry_turn`: one queued `session` attempt re-sends the last failed turn's message, resuming
the harness session the earlier turns recorded (epic 4 story 6, AC1-AC4, FR-13)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.use_cases.session_checks import NO_BUDGET
from orchestrator.application.use_cases.session_retry import NOT_FAILED, retry_turn
from orchestrator.application.use_cases.session_turn import NO_SESSION
from orchestrator.application.use_cases.session_view import SessionTurn
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.domain.errors import Conflict
from tests.unit.application.session_fixtures import BUILD, MODEL
from tests.unit.application.session_turn_fixtures import TurnWorld, a_result, a_turn_world
from tests.unit.application.test_conversation_messages import messages, session_turns, talking


def failed_world() -> TurnWorld:
    """Turns 1-3 recorded harness session `s-1`; turn 3 ended `error`."""
    world = a_turn_world()
    world.session.turn(1, session_id="s-1", message="one")
    world.session.turn(2, session_id="s-1", message="two")
    world.session.turn(3, session_id="s-1", message="three", status="error")
    world.session.world.engine.calls.clear()
    return world


def retry(world: TurnWorld) -> SessionTurn:
    return retry_turn(world.messages, world.session.world.run.id)


def refused(world: TurnWorld, text: str) -> None:
    engine = world.session.world.engine
    before = (world.session.world.attempts_of(BUILD), list(engine.calls))
    with pytest.raises(Conflict) as raised:
        retry(world)
    assert str(raised.value) == text
    assert (world.session.world.attempts_of(BUILD), list(engine.calls)) == before


def test_a_failed_turn_is_requeued_with_its_message_and_resumes_the_harness_session() -> None:
    world = failed_world()

    turn = retry(world)

    stored = world.attempt(turn.attempt_id)
    assert (stored.role, stored.status, stored.n) == ("session", "queued", 4)
    assert stored.message == "three"
    assert stored.started_at == world.session.world.clock.now()
    assert (stored.harness, stored.model) == ("claude", MODEL)
    assert (turn.turn, turn.status, turn.message) == (4, "queued", "three")
    engine = world.session.world.engine
    assert engine.calls == [("enqueue_session_turn", (world.session.world.run.id, stored.id))]
    assert engine.committed_when_called[-1] is True

    world.harness.results = [a_result()]
    world.run(stored.id)

    (call,) = world.harness.called("start_resume")
    assert call["session_id"] == "s-1"
    assert "three" in str(call)


@pytest.mark.parametrize("status", ["running", "queued"])
def test_an_open_turn_is_a_409(status: str) -> None:
    world = failed_world()
    world.session.turn(4, status=status, ended_at=None)

    refused(world, TURN_RUNNING)


def test_a_turn_that_ended_done_is_a_409() -> None:
    world = a_turn_world()
    world.session.turn(1, message="one")

    refused(world, NOT_FAILED)


def test_a_session_with_no_turn_is_a_409() -> None:
    refused(a_turn_world(), NOT_FAILED)


def test_no_open_session_is_a_409_and_nothing_reopens() -> None:
    world = failed_world()
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(run.model_copy(update={"senior_session": False}))
    records = len(world.session.world.ports.records.list_for_run(run.id))

    refused(world, NO_SESSION)

    assert len(world.session.world.ports.records.list_for_run(run.id)) == records


def test_a_run_with_no_row_at_its_park_is_a_409() -> None:
    world = failed_world()
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(run.model_copy(update={"park_path": None}))

    refused(world, NO_SESSION)


def test_no_budget_left_is_a_409() -> None:
    world = failed_world()
    run = world.session.world.stored_run()
    money = Decimal("1.00")
    world.session.world.ports.runs.update(
        run.model_copy(update={"budget_usd": money, "spend_usd": money, "gate_spend_usd": money})
    )

    refused(world, NO_BUDGET)


def test_the_run_is_read_under_the_row_lock() -> None:
    world = failed_world()

    retry(world)

    runs = world.session.world.ports.runs
    assert ("get_for_update", world.session.world.run.id) in runs.calls  # type: ignore[attr-defined]


def test_a_failed_enqueue_closes_the_new_attempt_and_raises() -> None:
    world = failed_world()
    world.session.world.engine.session_turn_error = RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        retry(world)

    stored = max(world.session.world.attempts_of(BUILD), key=lambda a: a.n)
    assert (stored.n, stored.status, stored.output_ref) == (4, "error", "queue unavailable")
    assert stored.ended_at == world.session.world.clock.now()


def test_a_failed_turn_on_a_conversation_stop_is_requeued() -> None:
    world = talking()
    (opening,) = session_turns(world)
    world.ports.attempts.update(
        opening.model_copy(update={"status": "error", "ended_at": world.clock.now()})
    )
    world.engine.calls.clear()

    turn = retry_turn(messages(world), world.run.id)

    stored = world.ports.attempts.get(turn.attempt_id)
    assert stored is not None
    assert (stored.status, stored.n, stored.message) == ("queued", opening.n + 1, opening.message)
    assert world.engine.calls == [("enqueue_session_turn", (world.run.id, stored.id))]


def test_an_ended_conversation_session_is_a_409_and_is_not_reopened() -> None:
    world = talking()
    (opening,) = session_turns(world)
    world.ports.attempts.update(
        opening.model_copy(update={"status": "error", "ended_at": world.clock.now()})
    )
    world.ports.runs.update(world.stored_run().model_copy(update={"senior_session": False}))
    world.engine.calls.clear()
    starts = [r for r in world.records() if r.event == "session_start"]

    with pytest.raises(Conflict) as raised:
        retry_turn(messages(world), world.run.id)

    assert str(raised.value) == NO_SESSION
    assert [r for r in world.records() if r.event == "session_start"] == starts
    assert world.stored_run().senior_session is False
    assert session_turns(world) == [
        opening.model_copy(update={"status": "error", "ended_at": world.clock.now()})
    ]
    assert world.engine.calls == []
