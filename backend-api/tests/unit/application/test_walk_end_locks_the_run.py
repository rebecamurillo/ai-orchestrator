"""The walk's own ends — `close_run` and `expire` — read the Run under its row lock (AD-8).

PR #26 review, 2026-11-27: unlocked, a cancel committed while the walker was closing was
written over with `done`, and the initiative advance then read `done` and started the next
workflow she had just cancelled away from.
"""

from __future__ import annotations

from orchestrator.application.steps import StepPorts
from orchestrator.application.use_cases.walk import WalkPorts, close_run, expire
from tests.unit.application.writer_fixtures import PAIR_PLAN, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import FakeRunRepository


def test_close_run_reads_the_run_under_its_row_lock() -> None:
    world = a_world("running", PAIR_PLAN, statuses={"plan": "done", "checkout": "done"})
    ports = WalkPorts(
        writers=world.ports, step=StepPorts(git=FakeGit(), clock=world.clock, work_dir="/work")
    )

    close_run(ports, world.run.id)

    runs = world.ports.runs
    assert isinstance(runs, FakeRunRepository)
    assert ("get_for_update", world.run.id) in runs.calls


def test_expire_reads_the_run_under_its_row_lock() -> None:
    world = a_world("cancelled", PAIR_PLAN)
    ports = WalkPorts(
        writers=world.ports, step=StepPorts(git=FakeGit(), clock=world.clock, work_dir="/work")
    )

    assert expire(ports, world.run.id) == "cancelled"

    runs = world.ports.runs
    assert isinstance(runs, FakeRunRepository)
    assert ("get_for_update", world.run.id) in runs.calls
