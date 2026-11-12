"""The walker's `attempt_row` step waits on an instance hold inside the one step (AD-30)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.instance_hold import InstanceHold
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from orchestrator.infrastructure.dbos.walker import HOLD_POLL_SECONDS, WalkerDeps, build_walk
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.dbos import FakeDurableEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.instance_hold import FakeInstanceHoldRepository


class Done:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx.row.path)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Done]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    done = Done()
    register("plan.check", done)
    register("git.worktree", done)
    yield done
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def test_the_step_polls_every_five_seconds_until_the_hold_ends(executor: Done) -> None:
    world = a_world("queued", PAIR_PLAN)
    holds = FakeInstanceHoldRepository(
        InstanceHold(
            id=new_id(),
            held_at=world.clock.now(),
            expires_at=world.clock.now() + timedelta(days=1),
            reason="upgrade",
        )
    )
    writers = replace(world.ports, holds=holds)
    sleeps: list[float] = []

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) == 2:  # noqa: PLR2004
            holds.delete_all()

    @contextmanager
    def open_ports() -> Iterator[WriterPorts]:
        yield writers

    engine = FakeDurableEngine()
    walk = build_walk(
        engine,
        WalkerDeps(
            open_ports=open_ports,
            step_ports=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir="/work"),
            human_wait_seconds=5,
            sleep=sleep,
        ),
    )

    walk(str(world.run.id))

    assert HOLD_POLL_SECONDS == 5  # noqa: PLR2004
    assert sleeps == [5, 5]
    assert holds.calls.count("get_shared") == 4  # noqa: PLR2004 — three tries on row 1, one on row 2
    assert executor.seen == ["plan", "checkout"]
    assert world.stored_run().status == "done"
    assert [name for kind, name in engine.declared if kind == "step"] == [
        "next_row",
        "attempt_row",
        "apply_result",
        "close_run",
        "expire",
    ]
    assert [name for kind, name in engine.declared if kind == "workflow"] == ["run_walk"]
