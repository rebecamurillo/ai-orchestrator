"""`use_cases/signal_apply.py`: `signal_run`'s two halves, split so a caller holding its own
unit of work (4-1's chat reply) applies a signal inside it and tells the engine after its
own commit (story 4-1, AD-8, AD-24)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.signal_apply import apply_signal, finish_signal
from orchestrator.domain.errors import Conflict
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import World, a_world

BUILD = "stories[0].build"
AFTER = "stories[1].after"


def blocked() -> World:
    return a_world(
        "needs_you",
        statuses={BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="which schema?",
        park_seq=3,
    )


def test_apply_writes_the_record_and_the_transition_but_neither_commits_nor_tells() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "use psycopg"}, stop=3)

    with world.ports.uow:
        applied = apply_signal(world.signal_ports, world.stored_run(), signal)

        assert world.ports.uow.calls == ["enter"]
    assert world.engine.calls == []
    assert applied.run.status == "running"
    assert applied.rule.run_event == "answer"
    assert world.status_of(BUILD) == "queued"
    (record,) = world.records()
    assert (record.event, record.actor, record.text) == ("answer", "operator", "use psycopg")


def test_the_actor_given_overrides_the_tables() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "fix X"})

    with world.ports.uow:
        apply_signal(world.signal_ports, world.stored_run(), signal, actor="chat")

    (record,) = world.records()
    assert record.actor == "chat"


def test_the_mode_is_defaulted_into_the_payload() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "fix X"})

    with world.ports.uow:
        apply_signal(world.signal_ports, world.stored_run(), signal)

    assert world.records()[0].payload["mode"] == "restart"


def test_a_signal_naming_another_stop_is_refused_before_anything_is_written() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "fix X"}, stop=2)

    with world.ports.uow, pytest.raises(Conflict, match="names stop 2"):
        apply_signal(world.signal_ports, world.stored_run(), signal)

    assert world.records() == []
    assert world.status_of(BUILD) == "blocked"


def test_a_signal_the_table_refuses_writes_nothing() -> None:
    world = blocked()
    signal = Signal(kind="continue")

    with world.ports.uow, pytest.raises(Conflict):
        apply_signal(world.signal_ports, world.stored_run(), signal)

    assert world.records() == []


def test_finish_tells_the_engine_when_the_signal_resumed_the_run() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "fix X"})
    with world.ports.uow:
        applied = apply_signal(world.signal_ports, world.stored_run(), signal)
        world.ports.uow.commit()

    outcome = finish_signal(world.signal_ports, world.run.id, signal, applied)

    assert outcome.resumed
    assert outcome.run == applied.run
    assert world.engine.calls == [("signal", (world.run.id, signal))]
    assert world.engine.committed_when_called == [True]


def test_finish_stops_the_workflow_of_a_cancelled_run() -> None:
    world = blocked()
    signal = Signal(kind="cancel")
    with world.ports.uow:
        applied = apply_signal(world.signal_ports, world.stored_run(), signal)
        world.ports.uow.commit()

    outcome = finish_signal(world.signal_ports, world.run.id, signal, applied)

    assert not outcome.resumed
    assert outcome.cancel_plan is not None
    assert world.engine.calls == [("cancel", world.run.id)]


def test_finish_enqueues_nothing_more_for_a_run_left_running() -> None:
    world = blocked()
    signal = Signal(kind="answer", payload={"text": "fix X"})
    with world.ports.uow:
        applied = apply_signal(world.signal_ports, world.stored_run(), signal)
        world.ports.uow.commit()

    finish_signal(world.signal_ports, world.run.id, signal, applied)

    assert [name for name, _ in world.engine.calls] == ["signal"]
