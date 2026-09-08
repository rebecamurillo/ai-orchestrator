"""`application/use_cases/walk_frame.py`: one Story frame, read once, as values (AD-17, AD-8).

The module is `walk.py`'s frame half, split out when `walk.py` reached the 400-line cap
`backend-api/AGENTS.md` declares. `tests/unit/application/test_walk_frame_anchors.py` covers
the same rules from the outside — through `run_row`, over the `StepContext` an executor is
handed — and stays the reading that matters. This module covers the three public functions
directly, so the split has coverage of its own: what `read_frame` collects, what
`frame_start_sha` skips past, and what `frame_anchors` builds out of the two.
"""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.use_cases.walk_frame import (
    INITIATIVE_FOLDER_INPUT,
    WalkFrame,
    frame_anchors,
    frame_start_sha,
    read_frame,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ids import new_id
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.git import FakeGit

BUILD = "stories[0].build"
SYNC = "stories[0].sync"
VERIFY = "stories[0].verify"
PUSH = "push"

SPEC_FOLDER = "docs/epic-1"
WORKTREE = "/work/acme/widget/wt"

START_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
END_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"


def a_run_environment(world: World) -> RunEnvironment:
    return RunEnvironment(
        run_id=world.run.id,
        project_slug="acme",
        repository_slug="widget",
        repository_url="https://github.test/acme/widget.git",
        default_branch="main",
        install_command="",
        bmad_version="1.0.0",
        spec_folder=SPEC_FOLDER,
    )


def an_epic_world(**over: object) -> World:
    return a_world("running", EPIC_PLAN, worktree_path=WORKTREE, **over)


def an_ended_attempt(n: int, **over: object) -> Attempt:
    """An Attempt as a value, for the two functions that take a sequence of them."""
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": new_id(),
        "step_run_id": new_id(),
        "n": n,
        "status": "done",
    }
    fields.update(over)
    return Attempt(**fields)  # type: ignore[arg-type]


# ── read_frame ──────────────────────────────────────────────────────────────


def test_a_row_outside_any_story_frame_reads_an_empty_frame() -> None:
    """`push` belongs to no Story frame, and an empty frame is what says so (AD-9)."""
    world = an_epic_world()

    frame = read_frame(world.ports, world.run.id, world.row(PUSH))

    assert frame == WalkFrame()


def test_a_frames_rows_are_read_in_plan_order() -> None:
    world = an_epic_world()

    frame = read_frame(world.ports, world.run.id, world.row(BUILD))

    assert [row.path for row in frame.rows] == [SYNC, BUILD, VERIFY, "stories[0].commit-guard"]


def test_every_attempt_of_every_row_of_the_frame_is_collected() -> None:
    """One reading, so the three questions asked of a frame cannot disagree about it."""
    world = an_epic_world()
    an_attempt(world, SYNC, 1)
    an_attempt(world, BUILD, 1)
    an_attempt(world, BUILD, 2)

    frame = read_frame(world.ports, world.run.id, world.row(VERIFY))

    assert [attempt.n for attempt in frame.attempts] == [1, 1, 2]


# ── frame_start_sha ─────────────────────────────────────────────────────────


def test_the_frames_start_sha_skips_the_attempts_that_recorded_none() -> None:
    """A frame's first row is `git.sync`, which records no commit — the whole rule."""
    attempts = (an_ended_attempt(1), an_ended_attempt(2, start_sha=START_SHA))

    assert frame_start_sha(attempts) == START_SHA


def test_a_frame_whose_attempts_all_recorded_none_has_no_start_sha() -> None:
    assert frame_start_sha((an_ended_attempt(1),)) is None
    assert frame_start_sha(()) is None


# ── frame_anchors ───────────────────────────────────────────────────────────


def test_the_anchor_set_carries_the_spec_folder_and_the_frozen_tests() -> None:
    world = an_epic_world()
    frame = WalkFrame(
        rows=(),
        attempts=(
            an_ended_attempt(1, start_sha=START_SHA, frozen_test_files=("tests/test_a.py",)),
        ),
    )

    rule = frame_anchors(FakeGit(), world.run, a_run_environment(world), frame)

    assert "tests/test_a.py" in rule.anchors
    assert any(anchor.startswith(SPEC_FOLDER) for anchor in rule.anchors)


def test_the_initiative_folder_comes_off_the_runs_own_inputs() -> None:
    """AD-17's `{initiative_folder}`: `epic@1` binds none, so a Run without one freezes no
    `epics.yaml` — and a Run with one has it read from here and nowhere else."""
    world = an_epic_world(inputs={INITIATIVE_FOLDER_INPUT: "docs/initiative"})

    rule = frame_anchors(FakeGit(), world.run, a_run_environment(world), WalkFrame())

    assert "docs/initiative/epics.yaml" in rule.anchors


def test_only_an_attempt_that_started_and_came_back_is_an_agent_range() -> None:
    """`end_sha` is written by the agent tail alone: both halves, or no range (AD-8)."""
    world = an_epic_world()
    frame = WalkFrame(
        attempts=(
            an_ended_attempt(1, start_sha=START_SHA),
            an_ended_attempt(2, start_sha=START_SHA, end_sha=END_SHA),
        )
    )

    rule = frame_anchors(FakeGit(), world.run, a_run_environment(world), frame)

    assert rule.ranges == ((START_SHA, END_SHA),)


def test_the_rule_is_diffed_inside_the_runs_own_worktree() -> None:
    world = an_epic_world()

    rule = frame_anchors(FakeGit(), world.run, a_run_environment(world), WalkFrame())

    assert rule.worktree == Path(WORKTREE)
