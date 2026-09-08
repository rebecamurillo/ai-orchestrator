"""`apply_step_result`'s own 5.9 trigger: the commit-guard row reaching `done` records a
trajectory, in the same unit of work — never any other row, and never twice.
"""

from __future__ import annotations

from dataclasses import replace

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.trajectories import FakeTrajectoryRepository

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
COMMIT_GUARD = "stories[0].commit-guard"

DONE = StepResult(status="done", gate="deterministic", output_ref="/work/logs/1.log")


def _world() -> World:
    return a_world(
        "running",
        EPIC_PLAN,
        statuses={
            "stories[0].sync": "done",
            BUILD: "done",
            VERIFY: "done",
            COMMIT_GUARD: "running",
        },
    )


def _seq(world: World, path: str) -> int:
    return world.row(path).seq


def test_the_commit_guard_row_reaching_done_records_one_trajectory() -> None:
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    an_attempt(world, COMMIT_GUARD, n=1, status="running")
    trajectories = FakeTrajectoryRepository()
    ports: WriterPorts = replace(world.ports, trajectories=trajectories)

    apply_step_result(ports, world.run.id, _seq(world, COMMIT_GUARD), DONE)

    assert len(trajectories.trajectories) == 1
    (trajectory,) = trajectories.trajectories
    assert trajectory.frame == "stories[0]"


def test_a_row_that_is_not_the_commit_guard_records_nothing() -> None:
    world = _world()
    world.ports.steps.update(world.row(VERIFY).model_copy(update={"status": "running"}))
    an_attempt(world, VERIFY, n=1, status="running")
    trajectories = FakeTrajectoryRepository()
    ports: WriterPorts = replace(world.ports, trajectories=trajectories)

    apply_step_result(ports, world.run.id, _seq(world, VERIFY), DONE)

    assert trajectories.trajectories == []


def test_a_commit_guard_row_reaching_done_twice_records_only_once() -> None:
    """A replay of the same durable step must not land a second trajectory (AD-19, AD-6)."""
    world = _world()
    an_attempt(
        world, BUILD, n=1, status="done", started_at=world.clock.now(), ended_at=world.clock.now()
    )
    an_attempt(world, COMMIT_GUARD, n=1, status="running")
    trajectories = FakeTrajectoryRepository()
    ports: WriterPorts = replace(world.ports, trajectories=trajectories)

    apply_step_result(ports, world.run.id, _seq(world, COMMIT_GUARD), DONE)
    # the row is `done` and the Run has moved on; a second application of the same result
    # is exactly what a durable-step replay after a restart looks like.
    world.ports.steps.update(world.row(COMMIT_GUARD).model_copy(update={"status": "running"}))
    an_attempt(world, COMMIT_GUARD, n=2, status="running")

    apply_step_result(ports, world.run.id, _seq(world, COMMIT_GUARD), DONE)

    assert len(trajectories.trajectories) == 1
