"""The walker's own half of 4.8: the Run's environment, resolved before the executor runs.

AD-9 closes `StepContext`'s field list and AD-8 says an executor never touches a repository,
so the reads happen in the walker's `attempt_row` step and travel in `StepPorts`. Two
properties settle that this is what actually happens: the executor is handed the environment
the deps resolved, and no *other* step asks for one — `next_row`, `apply_result`, `close_run`
and `expire` run no executor, so a read there would be a query per loop for nothing.

`tests/unit/test_dbos_walker.py` drives the same fake engine and proves the loop itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.dbos.walker import WalkerDeps, build_walk
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import an_environment

WAIT_SECONDS = 5
WORK_DIR = "/work"
KINDS = ("plan.check", "git.worktree")


class Recording:
    """An executor that answers `done` and keeps the ports it was handed."""

    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


class Reader:
    """Stands in for `read_run_environment`: records the Runs it was asked about."""

    def __init__(self) -> None:
        self.asked: list[UUID] = []
        self.environment = an_environment()

    def __call__(self, run_id: UUID) -> object:
        self.asked.append(run_id)
        return self.environment


@pytest.fixture
def registry() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    for kind in KINDS:
        register(kind, recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def deps_for(world: World, reader: Reader | None) -> WalkerDeps:
    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield world.ports

    return WalkerDeps(
        open_ports=open_ports,
        step_ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
        human_wait_seconds=WAIT_SECONDS,
        read_environment=reader,
    )


def walk(world: World, reader: Reader | None) -> None:
    engine = FakeDurableEngine()
    build_walk(engine, deps_for(world, reader))(str(world.run.id))


def test_the_executor_is_handed_the_environment_the_walker_resolved(
    registry: Recording,
) -> None:
    world = a_world("queued", PAIR_PLAN)
    reader = Reader()

    walk(world, reader)

    assert [context.ports.run_env for context in registry.seen] == [reader.environment] * 2


def test_the_environment_is_read_once_per_row_and_only_for_the_row_that_runs(
    registry: Recording,
) -> None:
    """Four of the five durable steps run no executor; a read there would buy nothing."""
    world = a_world("queued", PAIR_PLAN)
    reader = Reader()

    walk(world, reader)

    assert reader.asked == [world.run.id, world.run.id]


def test_a_process_that_resolves_no_environment_leaves_the_ports_as_they_were(
    registry: Recording,
) -> None:
    """Every unit test whose executors need none; the git kinds refuse rather than guess."""
    world = a_world("queued", PAIR_PLAN)

    walk(world, None)

    assert [context.ports.run_env for context in registry.seen] == [None, None]


def test_the_rest_of_the_ports_are_the_ones_the_composition_root_built(
    registry: Recording,
) -> None:
    world = a_world("queued", PAIR_PLAN)
    deps = deps_for(world, Reader())

    build_walk(FakeDurableEngine(), deps)(str(world.run.id))

    context = registry.seen[0]
    assert context.ports.git is deps.step_ports.git
    assert context.ports.work_dir == WORK_DIR
