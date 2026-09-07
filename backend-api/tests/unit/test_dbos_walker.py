"""`infrastructure/dbos/walker.py`: the loop, driven over the fake durable engine.

The walker is five decorated functions and a workflow that calls them, so a fake whose
decorators return the function untouched turns the whole walk into one ordinary call — and
the loop, its four branches and what it carries between iterations become assertable without
a Postgres. What this module cannot prove is durability itself: that each step runs once and
a restart replays the ones that finished is the engine's own, and it is proven in the e2e
stack against the real one.

The rules the steps call are `application/use_cases/walk.py`'s and are tested there. Here
they run for real over the shared fakes, so a walk that reaches `done` reaches it by moving
the same rows a real Run would.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.signal_run import signal_run
from orchestrator.application.use_cases.writers import RUN_EXPIRED, WriterPorts
from orchestrator.domain.values import Park, Signal, StepResult
from orchestrator.infrastructure.dbos.config import HUMAN_TOPIC
from orchestrator.infrastructure.dbos.walker import UNREADABLE, WalkerDeps, build_walk
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.git import FakeGit

WAIT_SECONDS = 5
WORK_DIR = "/work"
KINDS = ("plan.check", "git.worktree")
EXPECTED_STEPS = 5
EXPECTED_ROWS = 2


class Scripted:
    """An executor answering from a script, one result per call, then `done` for ever."""

    def __init__(self, *results: StepResult) -> None:
        self.results = list(results)
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        if self.results:
            return self.results.pop(0)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def registry() -> Iterator[None]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    yield
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def deps_for(world: World) -> WalkerDeps:
    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.ports

    return WalkerDeps(
        open_ports=open_ports,
        step_ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
        human_wait_seconds=WAIT_SECONDS,
    )


def register_all(executor: Any) -> None:
    for kind in KINDS:
        register(kind, executor)


class Resuming(FakeDurableEngine):
    """A durable engine whose `recv` also does what the Operator's signal really did first.

    `signal_run` writes and commits before the engine is told (AD-8), so a message arriving
    at the walker is always a signal that has *already* moved the Run and queued its row.
    Applying it here is what makes this a test of the walker's resume and not of a message.
    """

    def __init__(self, world: World, kind: str) -> None:
        super().__init__(messages=[{"kind": kind}])
        self._world = world
        self._kind = kind

    def recv(self, topic: str, timeout_seconds: int) -> Any:
        if self.messages:
            signal_run(self._world.signal_ports, self._world.run.id, Signal(kind=self._kind))
        return super().recv(topic, timeout_seconds)


def test_the_walk_declares_five_steps_and_one_workflow(registry: None) -> None:
    """Every side effect is inside a step, and the loop that calls them is the workflow."""
    engine = FakeDurableEngine()

    build_walk(engine, deps_for(a_world()))

    declared = [name for kind, name in engine.declared if kind == "step"]
    assert declared == ["next_row", "attempt_row", "apply_result", "close_run", "expire"]
    assert [name for kind, name in engine.declared if kind == "workflow"] == ["run_walk"]


def test_a_plan_whose_rows_pass_runs_in_order_and_ends_done(registry: None) -> None:
    executor = Scripted()
    register_all(executor)
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(FakeDurableEngine(), deps_for(world))

    walk(str(world.run.id))

    assert [ctx.row.path for ctx in executor.seen] == ["plan", "checkout"]
    assert world.stored_run().status == "done"
    assert [world.status_of(path) for path, _ in PAIR_PLAN] == ["done", "done"]
    assert all(len(world.attempts_of(path)) == 1 for path, _ in PAIR_PLAN)
    assert world.events() == ["start", "done"]


def test_a_parked_run_waits_in_one_recv_on_its_own_topic(registry: None) -> None:
    register_all(Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint())))
    world = a_world("queued", PAIR_PLAN)
    engine = FakeDurableEngine()
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    assert engine.recvs == [(HUMAN_TOPIC.format(run_id=world.run.id), WAIT_SECONDS)]


def test_the_signal_that_ends_the_wait_resumes_the_walk_at_the_queued_row(
    registry: None,
) -> None:
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    world = a_world("queued", PAIR_PLAN, {}, {"plan": {}})
    walk = build_walk(Resuming(world, "continue"), deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert [ctx.row.path for ctx in executor.seen] == ["plan", "plan", "checkout"]


def test_the_resumed_row_is_handed_the_signal_s_own_record(registry: None) -> None:
    """AD-9: the executor reads `resume_signal`, and only on the row the signal resumed."""
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(Resuming(world, "continue"), deps_for(world))

    walk(str(world.run.id))

    assert executor.seen[0].resume_signal is None
    resumed = executor.seen[1].resume_signal
    assert resumed is not None
    assert resumed.event == "continue"
    assert executor.seen[2].resume_signal is None


def test_a_wait_that_reaches_its_deadline_fails_the_run(registry: None) -> None:
    register_all(Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint())))
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(FakeDurableEngine(), deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "failed"
    assert world.records()[-1].text == RUN_EXPIRED


def test_a_run_that_fails_ends_the_walk_without_a_wait(registry: None) -> None:
    """`on_fail: fail` ends the Run; there is no stop for the Operator to answer."""
    register_all(Scripted(StepResult(status="error", gate="deterministic", reason="exit 1")))
    world = a_world("queued", PAIR_PLAN, {}, {"plan": {"on_fail": "fail"}})
    engine = FakeDurableEngine()
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "failed"
    assert engine.recvs == []


def test_a_run_with_nothing_left_to_run_is_closed_rather_than_left_open(
    registry: None,
) -> None:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "skipped"})
    walk = build_walk(FakeDurableEngine(), deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"


def a_checkpoint() -> Park:
    return Park(kind="checkpoint", reason="review the diff")


class Racing(FakeDurableEngine):
    """A `recv` that times out *after* the Operator's signal has already resumed the Run.

    The race the `expire` step exists for: `signal_run` commits and sends as the deadline
    passes. The walker must go on walking a Run that is running again, not end on a timeout
    that wrote nothing.
    """

    def __init__(self, world: World, kind: str) -> None:
        super().__init__()
        self._world = world
        self._kind = kind
        self._raced = False

    def recv(self, topic: str, timeout_seconds: int) -> Any:
        if not self._raced:
            self._raced = True
            signal_run(self._world.signal_ports, self._world.run.id, Signal(kind=self._kind))
        return super().recv(topic, timeout_seconds)


def test_a_deadline_a_signal_beat_does_not_abandon_the_run(registry: None) -> None:
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(Racing(world, "continue"), deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert [ctx.row.path for ctx in executor.seen] == ["plan", "plan", "checkout"]


def test_a_run_the_walk_cannot_go_on_with_waits_for_the_operator(registry: None) -> None:
    """`close_run` parks a stall, and a park is a stop: the walk waits where a signal lands."""
    register_all(Scripted(StepResult(status="error", gate="deterministic", reason="exit 1")))
    world = a_world("queued", PAIR_PLAN, {}, {"plan": {"on_fail": "escalate"}})
    engine = FakeDurableEngine()
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    # the wait was opened; this engine answers it with the deadline, so the park fields are
    # already cleared by the expiry — the record is where a park that happened is recorded
    assert engine.recvs == [(HUMAN_TOPIC.format(run_id=world.run.id), WAIT_SECONDS)]
    parked = world.records()[-2]
    assert parked.event == "internal"
    assert parked.path == "plan"


def test_a_stalled_run_a_signal_answers_carries_on(registry: None) -> None:
    executor = Scripted(StepResult(status="error", gate="deterministic", reason="exit 1"))
    register_all(executor)
    world = a_world("queued", PAIR_PLAN, {}, {"plan": {"on_fail": "escalate"}})
    walk = build_walk(Resuming(world, "retry"), deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert [ctx.row.path for ctx in executor.seen] == ["plan", "plan", "checkout"]


def test_a_message_the_walker_cannot_read_resumes_the_row_with_no_signal(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `KeyError` in the workflow body has no step to record it and no way to park."""
    configure_logging("info")
    executor = Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint()))
    register_all(executor)
    world = a_world("queued", PAIR_PLAN)
    engine = Unreadable(world)
    walk = build_walk(engine, deps_for(world))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert executor.seen[1].resume_signal is None
    assert UNREADABLE in capsys.readouterr().out


class Unreadable(Resuming):
    """The signal is applied, but the message that announces it carries no kind."""

    def __init__(self, world: World) -> None:
        super().__init__(world, "continue")
        self.messages = [{"note": "no kind here"}]
