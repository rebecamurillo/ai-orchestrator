"""`walk_context` resolves the story baseline a consult copies (story 1-5, spine AD-22,
2026-11-02): the row's lowest-`n` `agent` attempt that recorded a start SHA, read in the root
tree, so on a `workdir` row its `root_start_sha`."""

from __future__ import annotations

from typing import Any

from orchestrator.application.steps import StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.walk_context import context
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

BUILD = "stories[0].build"
OUTSIDE = "baseline"


def step_ports(world: World) -> StepPorts:
    return StepPorts(
        git=FakeGit(),
        clock=FakeClock(EPOCH),
        work_dir="/work",
        run_env=RunEnvironment(
            run_id=world.run.id,
            project_slug="acme",
            repository_slug="widgets",
            repository_url="https://github.com/acme/widgets.git",
            default_branch="main",
            bmad_version="6.11.0",
            spec_folder="specs",
        ),
    )


def baseline(world: World, path: str = BUILD) -> str | None:
    ctx = context(world.ports, step_ports(world), world.run, world.row(path).seq, None)
    assert ctx.ports.run_env is not None
    return ctx.ports.run_env.story_baseline_sha


def a_built_world(resolved: dict[str, Any] | None = None) -> World:
    return a_world("running", EPIC_PLAN, {BUILD: "running"}, {BUILD: resolved or {}, OUTSIDE: {}})


def test_the_first_agent_start_is_the_baseline() -> None:
    world = a_built_world()
    an_attempt(world, BUILD, n=1, role="consult", start_sha="c" * 40)
    an_attempt(world, BUILD, n=2, status="error")
    an_attempt(world, BUILD, n=3, status="error", start_sha="1" * 40)
    an_attempt(world, BUILD, n=4, start_sha="2" * 40)

    assert baseline(world) == "1" * 40


def test_a_workdir_row_reads_its_root_start() -> None:
    world = a_built_world({"workdir": "repos/member"})
    an_attempt(world, BUILD, n=1, status="error", start_sha="a" * 40, root_start_sha=None)
    an_attempt(world, BUILD, n=2, start_sha="b" * 40, root_start_sha="d" * 40)

    assert baseline(world) == "d" * 40


def test_no_baseline_before_any_agent_started() -> None:
    world = a_built_world()
    an_attempt(world, BUILD, n=1)

    assert baseline(world) is None


def test_a_row_outside_a_frame_is_resolved_too() -> None:
    world = a_built_world()
    an_attempt(world, OUTSIDE, n=1, start_sha="3" * 40)

    assert baseline(world, OUTSIDE) == "3" * 40
