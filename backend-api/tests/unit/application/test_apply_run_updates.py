"""`apply_step_result`'s `run_updates` half: the Run's own columns, written by the writer.

AD-8 gives an executor no way to write a Run, and AD-14 gives three kinds a side effect on
one. This module asserts the seam between those two facts: a result carries the values, the
writer applies exactly the fields the result named, and it does so inside the unit of work
the row's own transitions are already in — so the next row reads a committed value.
"""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import Park, RunUpdates, StepResult, Worktree
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt

WORKTREE = Worktree(
    branch="chore/bmad-init",
    path="/work/acme/widgets/wt/chore/bmad-init",
    created_branch=True,
    pushed=False,
)
COMPARE = "https://github.com/acme/widgets/compare/main...chore/bmad-init"


def a_world_on_its_first_row() -> World:
    world = a_world("running", PAIR_PLAN, {"plan": "running"})
    an_attempt(world, "plan")
    return world


def test_a_result_that_names_no_updates_leaves_the_run_alone() -> None:
    world = a_world_on_its_first_row()

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(status="done", gate="deterministic"),
    )

    run = world.ports.runs.get(world.run.id)
    assert run is not None
    assert run.worktree_path is None
    assert run.worktrees == ()
    assert run.compare_urls == ()


def test_the_worktree_a_row_opened_is_written_as_the_run_now_stands() -> None:
    world = a_world_on_its_first_row()

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(
            status="done",
            gate="deterministic",
            run_updates=RunUpdates(worktree_path=WORKTREE.path, worktrees=(WORKTREE,)),
        ),
    )

    run = world.ports.runs.get(world.run.id)
    assert run is not None
    assert run.worktree_path == WORKTREE.path
    assert run.worktrees == (WORKTREE,)
    assert isinstance(run.worktrees[0], Worktree)


def test_a_result_naming_one_column_leaves_the_other_two_as_they_were() -> None:
    """`pr.link` appends a URL; it says nothing about the worktree the Run is standing in."""
    world = a_world(
        "running",
        PAIR_PLAN,
        {"plan": "done", "checkout": "running"},
        worktree_path=WORKTREE.path,
        worktrees=(WORKTREE,),
    )
    an_attempt(world, "checkout")

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(
            status="done",
            gate="liveness",
            run_updates=RunUpdates(compare_urls=(COMPARE,)),
        ),
    )

    run = world.ports.runs.get(world.run.id)
    assert run is not None
    assert run.compare_urls == (COMPARE,)
    assert run.worktree_path == WORKTREE.path
    assert run.worktrees == (WORKTREE,)


def test_a_park_still_records_the_worktree_the_row_made() -> None:
    """AD-13's `cancel` removes a worktree by reading `run.worktrees[]`, parked or not."""
    world = a_world_on_its_first_row()

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(
            status="error",
            gate="deterministic",
            reason="install failed: exit 1",
            park=Park(kind="misconfigured", reason="install failed: exit 1"),
            run_updates=RunUpdates(worktree_path=WORKTREE.path, worktrees=(WORKTREE,)),
        ),
    )

    run = world.ports.runs.get(world.run.id)
    assert run is not None
    assert run.status == "needs_you"
    assert run.worktrees == (WORKTREE,)
