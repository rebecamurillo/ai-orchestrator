"""AD-24 where a client meets it: through `handle_signal`, across real signals, and at `start`."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_events import run_event
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.signals import handle_signal
from orchestrator.application.use_cases.writers import park_run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Park, Signal
from tests.unit.application.test_handle_signal import effect_ports
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, build_run
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

BUILD = "stories[0].build"
STALE = 1
CURRENT = 2
NAMES_CURRENT = "the Run is at stop 2"


def refused_message(world: World, signal: Signal) -> str:
    before = world.events()
    with pytest.raises(Conflict) as refused:
        handle_signal(effect_ports(world), world.run.id, signal)
    assert world.events() == before
    assert world.engine.calls == []
    return str(refused.value)


def at_stop(kind: str, row_status: str, **over: object) -> World:
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {BUILD: row_status},  # type: ignore[dict-item]
        park_kind=kind,
        park_path=BUILD,
        park_reason="why it stopped",
        park_seq=CURRENT,
        **over,
    )


def test_a_stale_answer_on_a_running_run_names_the_current_stop() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, park_seq=CURRENT)

    assert NAMES_CURRENT in refused_message(world, Signal(kind="answer", stop=STALE))


def test_a_stale_answer_at_a_stop_that_does_not_admit_answers_names_the_stop() -> None:
    world = at_stop("verify_failed", "error")

    message = refused_message(world, Signal(kind="answer", stop=STALE))

    assert NAMES_CURRENT in message
    assert "verify_failed" in message


def test_a_stale_accept_is_refused_as_stale_before_its_file_list_is_compared() -> None:
    world = at_stop("protected_path", "error")

    message = refused_message(
        world, Signal(kind="continue", payload={"files": ["other.py"]}, stop=STALE)
    )

    assert NAMES_CURRENT in message


def test_a_stale_answer_during_a_terminal_session_names_the_stop() -> None:
    world = at_stop("blocked", "blocked", terminal_session=True)

    assert NAMES_CURRENT in refused_message(world, Signal(kind="answer", stop=STALE))


def test_a_refusal_at_a_stop_with_no_row_does_not_print_an_empty_path() -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {},
        park_kind="dependency",
        park_path=None,
        park_reason="run x ended failed",
        park_seq=CURRENT,
    )

    message = refused_message(world, Signal(kind="continue", stop=STALE))

    assert message.endswith(": dependency")
    assert "None" not in message


def test_start_refuses_a_stop_it_does_not_match_and_enqueues_nothing() -> None:
    world = a_world("queued", EPIC_PLAN, {})

    with pytest.raises(Conflict, match="the Run is at stop 0"):
        signal_run(world.signal_ports, world.run.id, Signal(kind="start", stop=CURRENT))

    assert world.engine.calls == []


def test_the_number_survives_an_answer_and_the_next_stop_takes_the_next_one() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"})
    with world.ports.uow:
        park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="one", path=BUILD))
        world.ports.uow.commit()
    world.ports.steps.update(world.row(BUILD).model_copy(update={"status": "blocked"}))

    signal_run(
        world.signal_ports,
        world.run.id,
        Signal(kind="answer", payload={"text": "go"}, stop=STALE),
    )
    assert world.stored_run().park_kind is None
    assert world.stored_run().park_seq == STALE

    with world.ports.uow:
        park_run(world.ports, world.stored_run(), Park(kind="blocked", reason="two", path=BUILD))
        world.ports.uow.commit()
    assert world.stored_run().park_seq == CURRENT


def test_the_events_read_reports_the_runs_own_number() -> None:
    run = build_run("needs_you", park_kind="blocked", park_path=BUILD, park_seq=CURRENT)
    ports = RunReadPorts(runs=FakeRunRepository([run]), steps=FakeStepRunRepository([]))

    assert run_event(ports, run.id).park_seq == CURRENT
