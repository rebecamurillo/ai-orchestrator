"""`GET /runs/{id}/session` gains the turns (story 2-5, AD-23): whether one is running, and
each of the session's attempts as a numbered turn with its message and reply."""

from __future__ import annotations

from decimal import Decimal

from orchestrator.application.use_cases.session_view import SessionTurn, session_view, turn_of
from orchestrator.application.use_cases.signals import session_ports
from tests.unit.application.session_turn_fixtures import a_turn_world
from tests.unit.fakes.clock import EPOCH


def test_the_view_lists_the_sessions_turns_in_order() -> None:
    world = a_turn_world()
    first = world.session.turn(
        1, message="Why?", reply="Because.", exit_code=0, cost_usd=Decimal("0.1")
    )
    second = world.session.turn(2, message="And?", status="running", ended_at=None)
    world.session.turn(3, role="agent")

    found = session_view(session_ports(world.session.ports), world.session.world.run.id)

    assert found.turn_running is True
    assert found.turns == (
        SessionTurn(
            attempt_id=first.id,
            turn=1,
            status="done",
            message="Why?",
            reply="Because.",
            started_at=first.started_at,
            ended_at=first.ended_at,
            exit_code=0,
            cost_usd=Decimal("0.1"),
        ),
        SessionTurn(
            attempt_id=second.id,
            turn=2,
            status="running",
            message="And?",
            reply="",
            started_at=second.started_at,
            ended_at=None,
            exit_code=None,
            cost_usd=None,
        ),
    )


def test_a_session_with_every_turn_closed_runs_none() -> None:
    world = a_turn_world()
    world.session.turn(1)

    found = session_view(session_ports(world.session.ports), world.session.world.run.id)

    assert found.turn_running is False
    assert [turn.turn for turn in found.turns] == [1]


def test_a_stop_with_no_session_has_no_turns() -> None:
    world = a_turn_world(start=False)

    found = session_view(session_ports(world.session.ports), world.session.world.run.id)

    assert (found.turn_running, found.turns) == (False, ())


def test_one_turn_reads_its_own_number() -> None:
    world = a_turn_world()
    attempt = world.session.turn(4, message="go", started_at=EPOCH)
    third = 3

    assert turn_of(attempt, third).turn == third
