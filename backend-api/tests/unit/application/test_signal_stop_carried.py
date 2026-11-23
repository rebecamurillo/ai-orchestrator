"""The engine is told the stop a signal was validated against (story 2, epic 4; AD-13)."""

from __future__ import annotations

import pytest

from orchestrator.application.use_cases.signal_apply import apply_signal, finish_signal
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.values import Signal
from tests.unit.application.writer_fixtures import World, a_world

BUILD = "stories[0].build"
STOP = 3


def _blocked() -> World:
    return a_world(
        "needs_you",
        statuses={BUILD: "blocked"},
        park_kind="blocked",
        park_path=BUILD,
        park_reason="which schema?",
        park_seq=STOP,
    )


@pytest.mark.parametrize(
    "signal",
    [
        Signal(kind="answer", payload={"text": "x"}),
        Signal(kind="answer", payload={"text": "x"}, stop=STOP),
    ],
)
def test_the_engine_signal_carries_the_runs_park_seq(signal: Signal) -> None:
    world = _blocked()

    signal_run(world.signal_ports, world.run.id, signal)

    assert world.engine.calls == [
        ("signal", (world.run.id, signal.model_copy(update={"stop": STOP})))
    ]


def test_a_continue_with_no_stop_reaches_the_engine_with_the_runs_park_seq() -> None:
    world = a_world(
        "needs_you",
        statuses={BUILD: "checkpoint"},
        park_kind="checkpoint",
        park_path=BUILD,
        park_seq=STOP,
    )

    signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))

    assert world.engine.calls == [("signal", (world.run.id, Signal(kind="continue", stop=STOP)))]


def test_apply_signal_records_the_stop_of_the_run_it_was_handed() -> None:
    world = _blocked()
    signal = Signal(kind="answer", payload={"text": "x"})

    with world.ports.uow:
        applied = apply_signal(world.signal_ports, world.stored_run(), signal)
        world.ports.uow.commit()
    finish_signal(world.signal_ports, world.run.id, signal, applied)

    assert applied.stop == STOP
