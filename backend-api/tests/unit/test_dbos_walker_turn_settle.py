"""After a resuming message the walk waits for a killed turn (epic 4 story 5, AC4, AC5)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.domain.values import Signal, StepResult
from orchestrator.infrastructure.dbos.walker import (
    HOLD_POLL_SECONDS,
    WAITING_FOR_KILLED_TURN,
    WalkerDeps,
    build_walk,
)
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.test_dbos_walker import Scripted, a_checkpoint, deps_for, register_all, registry

__all__ = ["registry"]

CURRENT_STOP = 4
ANSWERS = [1, 1, 0]


class Counting(FakeDurableEngine):
    """The `open_turns` step answers from a script; every other step is the real one."""

    def __init__(self, answers: list[int], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.answers = list(answers)
        self.asked = 0

    def step(self, function: Any) -> Any:
        if function.__name__ != "open_turns":
            return super().step(function)

        def open_turns(run_id: str) -> int:
            self.asked += 1
            return self.answers.pop(0)

        return super().step(open_turns)


def _world() -> tuple[Scripted, World]:
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    return executor, a_world("queued", PAIR_PLAN, park_seq=3)


def _applying(world: World, kind: str = "continue") -> Callable[[Any], None]:
    """What the Operator's signal did before the engine was told (AD-8)."""

    def apply(_: Any) -> None:
        stop = None if kind == "cancel" else CURRENT_STOP
        signal_run(world.signal_ports, world.run.id, Signal(kind=kind, stop=stop))  # type: ignore[arg-type]

    return apply


def _walk(world: World, engine: FakeDurableEngine, sleeps: list[float]) -> None:
    deps: WalkerDeps = replace(deps_for(world), sleep=sleeps.append)
    build_walk(engine, deps)(str(world.run.id))


def test_the_walk_waits_until_the_killed_turn_has_closed(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    executor, world = _world()
    engine = Counting(
        [1, 1, 0],
        messages=[{"kind": "continue", "stop": CURRENT_STOP}],
        before_recv=_applying(world),
    )
    sleeps: list[float] = []

    _walk(world, engine, sleeps)

    assert engine.asked == len(ANSWERS)
    assert sleeps == [HOLD_POLL_SECONDS] * 2
    out = capsys.readouterr().out
    assert out.count(WAITING_FOR_KILLED_TURN) == 1
    assert '"count": 1' in out and str(world.run.id) in out
    assert [ctx.row.path for ctx in executor.seen] == ["plan", "plan", "checkout"]
    assert world.stored_run().status == "done"


def test_no_open_turn_means_no_sleep(registry: None) -> None:
    _, world = _world()
    engine = Counting(
        [0], messages=[{"kind": "continue", "stop": CURRENT_STOP}], before_recv=_applying(world)
    )
    sleeps: list[float] = []

    _walk(world, engine, sleeps)

    assert (engine.asked, sleeps) == (1, [])


def test_the_cancel_wake_up_never_waits(registry: None) -> None:
    _, world = _world()
    engine = Counting([], messages=[{"kind": "cancel"}], before_recv=_applying(world, "cancel"))
    sleeps: list[float] = []

    _walk(world, engine, sleeps)

    assert (engine.asked, sleeps) == (0, [])
    assert world.stored_run().status == "cancelled"


def test_the_open_turns_step_counts_a_running_session_attempt(registry: None) -> None:
    _, world = _world()
    an_attempt(world, "checkout", role="session", status="running")
    seen: list[int] = []

    class Spy(FakeDurableEngine):
        def step(self, function: Any) -> Any:
            wrapped: Callable[[str], Any] = super().step(function)
            if function.__name__ != "open_turns":
                return wrapped

            def spy(run_id: str) -> Any:
                seen.append(wrapped(run_id))
                return 0

            return spy

    engine = Spy(
        messages=[{"kind": "continue", "stop": CURRENT_STOP}], before_recv=_applying(world)
    )
    _walk(world, engine, [])

    assert seen == [1]
