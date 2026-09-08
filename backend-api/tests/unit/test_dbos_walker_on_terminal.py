"""`infrastructure/dbos/walker.py`'s second completion hook (SPEC CAP-8): `on_terminal`.

A new module, not an addition to `test_dbos_walker_on_finished.py` — that one is frozen and
already proves `run_finished`'s own `DONE`-only gate untouched; this one proves the second,
independent hook this story adds beside it, on the wider `done`/`failed`/`cancelled` set.
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
from orchestrator.infrastructure.dbos.walker import (
    ON_TERMINAL_HOOK_FAILED,
    RUN_FINISHED_HOOK_FAILED,
    WalkerDeps,
    _finish,
    build_walk,
)
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
            raise RuntimeError("readiness evaluation exploded")


def deps_for(
    world: World,
    *,
    run_finished: RecordingHook | None = None,
    on_terminal: RecordingHook | None = None,
) -> WalkerDeps:
    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.ports

    return WalkerDeps(
        open_ports=open_ports,
        step_ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
        human_wait_seconds=5,
        run_finished=run_finished,
        on_terminal=on_terminal,
    )


def a_checkpoint() -> Park:
    return Park(kind="checkpoint", reason="review the diff")


def test_on_terminal_fires_when_a_run_reaches_done(registry: None) -> None:
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    hook = RecordingHook()
    walk = build_walk(FakeDurableEngine(), deps_for(world, on_terminal=hook))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert hook.calls == [world.run.id]


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_finish_calls_on_terminal_for_every_terminal_status_but_done(
    registry: None, status: str
) -> None:
    """`_finish` is the one function `TERMINAL` governs — proven directly, since driving a
    full walk to `failed` or `cancelled` through `close_run`/`apply_result` (rather than the
    `expire` path, which never calls either hook at all — the same reason
    `test_dbos_walker_on_finished.py`'s own `failed`-via-expire scenario sees no
    `run_finished` call either) is not what this module needs to prove."""
    world = a_world("queued", PAIR_PLAN)
    finished = RecordingHook()
    terminal = RecordingHook()
    deps = deps_for(world, run_finished=finished, on_terminal=terminal)

    _finish(deps, str(world.run.id), status)

    assert finished.calls == []
    assert terminal.calls == [world.run.id]


def test_on_terminal_and_run_finished_both_fire_on_done(registry: None) -> None:
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    finished = RecordingHook()
    terminal = RecordingHook()
    walk = build_walk(
        FakeDurableEngine(), deps_for(world, run_finished=finished, on_terminal=terminal)
    )

    walk(str(world.run.id))

    assert finished.calls == [world.run.id]
    assert terminal.calls == [world.run.id]


def test_finish_calls_neither_hook_for_a_non_terminal_status(registry: None) -> None:
    world = a_world("queued", PAIR_PLAN)
    finished = RecordingHook()
    terminal = RecordingHook()
    deps = deps_for(world, run_finished=finished, on_terminal=terminal)

    _finish(deps, str(world.run.id), "running")

    assert finished.calls == []
    assert terminal.calls == []


def test_no_on_terminal_hook_wired_is_not_an_error(registry: None) -> None:
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    walk = build_walk(FakeDurableEngine(), deps_for(world, on_terminal=None))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"


def test_an_on_terminal_hook_that_raises_is_logged_and_does_not_end_the_walk_early(
    registry: None, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_logging("info")
    register_all(Scripted())
    world = a_world("queued", PAIR_PLAN)
    hook = RecordingHook(raises=True)
    walk = build_walk(FakeDurableEngine(), deps_for(world, on_terminal=hook))

    walk(str(world.run.id))

    assert world.stored_run().status == "done"
    assert hook.calls == [world.run.id]
    assert ON_TERMINAL_HOOK_FAILED in capsys.readouterr().out
    assert RUN_FINISHED_HOOK_FAILED not in capsys.readouterr().out
