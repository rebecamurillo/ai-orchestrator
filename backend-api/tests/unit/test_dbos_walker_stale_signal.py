"""The walk discards a message written for an earlier stop (story 2, epic 4; AD-13 amended)."""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.values import Signal, StepResult
from orchestrator.infrastructure.dbos.walker import STALE_SIGNAL, build_walk
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.test_dbos_walker import Scripted, a_checkpoint, deps_for, register_all, registry

__all__ = ["registry"]

CURRENT_STOP = 4
TWO_RECVS = 2


def _parked_world() -> tuple[Scripted, World]:
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    return executor, a_world("queued", PAIR_PLAN, park_seq=3)


def test_a_message_for_an_earlier_stop_is_discarded_and_the_walk_waits_again(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    executor, world = _parked_world()

    def apply_when_current(message: Any) -> None:
        if message["stop"] == CURRENT_STOP:
            signal_run(world.signal_ports, world.run.id, Signal(kind="continue", stop=CURRENT_STOP))

    engine = FakeDurableEngine(
        messages=[{"kind": "continue", "stop": 3}, {"kind": "continue", "stop": 4}],
        before_recv=apply_when_current,
    )
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    out = capsys.readouterr().out
    assert STALE_SIGNAL in out
    assert '"stop": 3' in out and '"current_stop": 4' in out
    assert len(engine.recvs) == TWO_RECVS
    assert [ctx.row.path for ctx in executor.seen] == ["plan", "plan", "checkout"]
    assert executor.seen[1].resume_signal is not None
    assert executor.seen[1].resume_signal.event == "continue"
    assert world.stored_run().status == "done"


def test_a_message_with_no_stop_is_never_checked(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    _, world = _parked_world()
    steps_called: list[str] = []

    class Spy(FakeDurableEngine):
        def step(self, function: Any) -> Any:
            if function.__name__ != "current_stop":
                return super().step(function)

            def spy(run_id: str) -> int:
                steps_called.append(run_id)
                return int(function(run_id))

            spy.__name__ = "current_stop"
            return super().step(spy)

    def cancel_first(_: Any) -> None:
        signal_run(world.signal_ports, world.run.id, Signal(kind="cancel"))

    engine = Spy(messages=[{"kind": "cancel"}], before_recv=cancel_first)
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    assert steps_called == []
    assert STALE_SIGNAL not in capsys.readouterr().out
    assert world.stored_run().status == "cancelled"


def test_a_stop_that_is_not_an_integer_reads_as_no_stop(registry: None) -> None:
    _, world = _parked_world()

    def apply(_: Any) -> None:
        signal_run(world.signal_ports, world.run.id, Signal(kind="continue"))

    engine = FakeDurableEngine(messages=[{"kind": "continue", "stop": "4"}], before_recv=apply)
    build_walk(engine, deps_for(world))(str(world.run.id))

    assert len(engine.recvs) == 1
    assert world.stored_run().status == "done"


def test_the_walk_declares_current_stop_last(registry: None) -> None:
    engine = FakeDurableEngine()
    build_walk(engine, deps_for(a_world()))
    assert [n for k, n in engine.declared if k == "step"][-1] == "current_stop"
