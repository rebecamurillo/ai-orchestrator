"""`infrastructure/dbos/walker.py`'s completion hook (4.10): called from inside an existing
step, never as a sixth one — `test_dbos_walker.py::
test_the_walk_declares_five_steps_and_one_workflow` pins the walk at exactly five steps, and
that test is frozen (hard rule 1). This module proves the hook fires exactly when a step of
the walk leaves the Run `done`, is not fired otherwise, and that a hook which raises is
logged and swallowed rather than let through to end the walk.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.values import Park, StepResult
from orchestrator.infrastructure.dbos.walker import RUN_FINISHED_HOOK_FAILED, WalkerDeps, build_walk
from orchestrator.infrastructure.logging import configure_logging
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"
KINDS = ("plan.check", "git.worktree")


class Scripted:
    def __init__(self, *results: StepResult) -> None:
        self.results = list(results)

    def execute(self, ctx: StepContext) -> StepResult:
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


def register_all(executor: Any) -> None:
    for kind in KINDS:
        register(kind, executor)


class RecordingHook:
    def __init__(self, *, raises: bool = False) -> None:
        self.calls: list[UUID] = []
        self.raises = raises

    def __call__(self, run_id: UUID) -> None:
        self.calls.append(run_id)
        if self.raises:
            raise RuntimeError("clone check exploded")


def deps_for(world: World, run_finished: RecordingHook | None = None) -> WalkerDeps:
    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.ports

    return WalkerDeps(
        open_ports=open_ports,
        step_ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
        human_wait_seconds=5,
        run_finished=run_finished,
    )


def test_the_hook_is_called_once_a_run_reaches_done(registry: None) -> None:
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    hook = RecordingHook()
    walk = build_walk(FakeDurableEngine(), deps_for(world, hook))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert hook.calls == [world.run.id]


def test_the_hook_is_not_called_when_the_run_does_not_reach_done(registry: None) -> None:
    """A parked wait whose deadline passes ends the walk `failed`, never `done`."""
    register_all(Scripted(StepResult(status="checkpoint", gate="human", park=a_checkpoint())))
    world = a_world("queued", PAIR_PLAN)
    hook = RecordingHook()
    walk = build_walk(FakeDurableEngine(), deps_for(world, hook))

    walk(str(world.run.id))

    assert world.stored_run().status == "failed"
    assert hook.calls == []


def a_checkpoint() -> Park:
    return Park(kind="checkpoint", reason="review the diff")


def test_no_hook_wired_is_not_an_error(registry: None) -> None:
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(FakeDurableEngine(), deps_for(world, run_finished=None))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"


def test_a_hook_that_raises_is_logged_and_does_not_end_the_walk_early(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    hook = RecordingHook(raises=True)
    walk = build_walk(FakeDurableEngine(), deps_for(world, hook))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert hook.calls == [world.run.id]
    assert RUN_FINISHED_HOOK_FAILED in capsys.readouterr().out
