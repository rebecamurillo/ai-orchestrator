"""`post_message`: one queued `session` attempt per message, then the engine (story 2-5,
AD-8, AD-23). It reads the Run under the row lock, refuses before writing, commits, and only
then enqueues; a failed enqueue closes the attempt it wrote."""

from __future__ import annotations

from decimal import Decimal

import pytest

from orchestrator.application.use_cases.session_checks import NO_BUDGET
from orchestrator.application.use_cases.session_turn import EMPTY_MESSAGE, NO_SESSION
from orchestrator.application.use_cases.signal_effects import TURN_RUNNING
from orchestrator.domain.errors import Conflict, Invalid
from tests.unit.application.session_fixtures import BUILD, MODEL
from tests.unit.application.session_turn_fixtures import TurnWorld, a_turn_world


def refused(world: TurnWorld, error: type[Exception], text: str = "go") -> str:
    before = (
        world.session.world.stored_run(),
        world.session.world.attempts_of(BUILD),
        list(world.session.world.engine.calls),
    )

    with pytest.raises(error) as raised:
        world.post(text)

    after = (
        world.session.world.stored_run(),
        world.session.world.attempts_of(BUILD),
        list(world.session.world.engine.calls),
    )
    assert after == before
    return str(raised.value)


def test_a_message_queues_one_session_attempt_and_enqueues_its_turn() -> None:
    world = a_turn_world()
    earlier = world.session.turn(1)

    posted = world.post("Why is the route missing?")

    stored = world.attempt(posted.attempt_id)
    assert (stored.role, stored.status, stored.n) == ("session", "queued", earlier.n + 1)
    assert stored.message == "Why is the route missing?"
    assert (stored.harness, stored.model) == ("claude", MODEL)
    assert stored.started_at == world.session.world.clock.now()
    assert stored.ended_at is None
    engine = world.session.world.engine
    assert engine.calls[-1] == ("enqueue_session_turn", (world.session.world.run.id, stored.id))
    assert engine.committed_when_called[-1] is True
    assert (posted.turn, posted.status, posted.message) == (2, "queued", stored.message)


def test_the_run_is_read_under_the_row_lock() -> None:
    world = a_turn_world()
    runs = world.session.world.ports.runs

    world.post()

    assert ("get_for_update", world.session.world.run.id) in runs.calls  # type: ignore[attr-defined]


def test_no_open_session_is_a_409() -> None:
    world = a_turn_world(start=False)

    assert refused(world, Conflict) == NO_SESSION


def test_a_terminal_run_has_no_open_session() -> None:
    world = a_turn_world()
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(run.model_copy(update={"status": "cancelled"}))

    assert refused(world, Conflict) == NO_SESSION


@pytest.mark.parametrize("text", ["", "   \n "])
def test_an_empty_message_is_a_422(text: str) -> None:
    assert refused(a_turn_world(), Invalid, text) == EMPTY_MESSAGE


def test_a_message_while_a_turn_is_open_is_a_409() -> None:
    world = a_turn_world()
    world.session.turn(1, ended_at=None, status="running")

    assert refused(world, Conflict) == TURN_RUNNING


def test_a_message_with_no_budget_left_is_a_409() -> None:
    world = a_turn_world()
    run = world.session.world.stored_run()
    world.session.world.ports.runs.update(
        run.model_copy(
            update={
                "budget_usd": Decimal("1.00"),
                "spend_usd": Decimal("1.00"),
                "gate_spend_usd": Decimal("1.00"),
            }
        )
    )

    assert refused(world, Conflict) == NO_BUDGET


def test_a_run_with_no_budget_set_takes_a_message() -> None:
    world = a_turn_world(budget_usd=None)

    assert world.post().status == "queued"


def test_a_failed_enqueue_closes_the_attempt_with_the_engines_words() -> None:
    world = a_turn_world()
    world.session.world.engine.session_turn_error = RuntimeError("queue unavailable")

    with pytest.raises(RuntimeError, match="queue unavailable"):
        world.post()

    (stored,) = world.session.world.attempts_of(BUILD)
    assert (stored.status, stored.output_ref) == ("error", "queue unavailable")
    assert stored.ended_at == world.session.world.clock.now()
    assert world.session.world.stored_run().status == "needs_you"
