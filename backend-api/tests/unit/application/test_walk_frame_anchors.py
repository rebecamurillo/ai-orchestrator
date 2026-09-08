"""The walker resolving one Story frame's anchors and agent ranges (AD-17, AD-8).

`walk._context` is the only place holding both the frame's rows and the repositories, so it
is where AD-17's three frame facts are read: which spec folders the frame's rows name, the
frozen test set of its lowest-`n` attempt that recorded a commit, and every `start_sha ..
end_sha` an attempt of the frame recorded. They travel to the two call sites as one frozen
value each — `RunEnvironment.anchors` for the agent tail, `StepPorts.protected_paths` for the
commit-guard — which is the move `verify_failure` and `frame_start_sha` already make: the
executor reads a value and never a repository.

`_frame_start_sha` is corrected here too. AD-17 names "the frame's lowest-`n` attempt that
has a `start_sha`", and a Story frame's first row is `git.sync`, whose attempt records none.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.application.rules.protected_paths import FrameAnchors
from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.walk import WalkPorts, run_row
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import (
    EPIC_PLAN,
    INITIATIVE_PLAN,
    World,
    a_world,
    an_attempt,
)
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit

WORK_DIR = "/work"
WORKTREE = "/work/acme/widgets/wt/feat-x"
SPEC_FOLDER = "specs/notifications"
OTHER_FOLDER = "_bmad-output/mvp/epic-2"
INITIATIVE = "_bmad-output/mvp"
SYNC = "stories[0].sync"
BUILD = "stories[0].build"
FROZEN = ("tests/unit/test_a.py",)
START, END = "a" * 40, "b" * 40


class Recording:
    """An executor that answers `done` and keeps the context it was handed."""

    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    """Every kind this module's plans hold, bound to one recording executor."""
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    for kind in ("agent", "git.sync", "git.commit"):
        register(kind, recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def ports_of(world: World, environment: RunEnvironment | None) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(
            git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR, run_env=environment
        ),
    )


def an_environment(**over: object) -> RunEnvironment:
    fields: dict[str, object] = {
        "run_id": new_id(),
        "project_slug": "acme",
        "repository_slug": "widgets",
        "repository_url": "https://github.com/acme/widgets.git",
        "default_branch": "main",
        "install_command": "",
        "bmad_version": "6.11.0",
        "spec_folder": SPEC_FOLDER,
    }
    fields.update(over)
    return RunEnvironment(**fields)  # type: ignore[arg-type]


def a_story_frame(**over: object) -> World:
    """An `epic@1` Run standing on `stories[0].build`, its `sync` row already done."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {SYNC: "done", BUILD: "running"},
        {BUILD: {"spec_folder": SPEC_FOLDER}},
        worktree_path=WORKTREE,
        **over,
    )
    return world


def seen_context(world: World, path: str, environment: RunEnvironment | None) -> StepContext:
    ports = ports_of(world, environment)
    run_row(ports, world.run.id, world.row(path).seq)
    recording = EXECUTORS[world.row(path).kind]
    assert isinstance(recording, Recording)
    return recording.seen[-1]


def environment_of(context: StepContext) -> RunEnvironment:
    environment = context.ports.run_env
    assert environment is not None
    return environment


def anchors_of(context: StepContext) -> FrameAnchors:
    rule = context.ports.protected_paths
    assert isinstance(rule, FrameAnchors)
    return rule


# ── `_frame_start_sha`, corrected ───────────────────────────────────────────


@pytest.mark.usefixtures("executor")
def test_the_frame_reads_past_an_attempt_that_recorded_no_commit() -> None:
    """AD-17's own words: the frame's lowest-`n` attempt that *has* a `start_sha`. A Story
    frame's first row is `git.sync`, and `git.sync` never records one."""
    world = a_story_frame()
    an_attempt(world, SYNC, n=1, status="done", ended_at=EPOCH)
    an_attempt(world, BUILD, n=1, start_sha=START)

    assert seen_context(world, BUILD, an_environment()).frame_start_sha == START


@pytest.mark.usefixtures("executor")
def test_a_frame_whose_earlier_row_did_record_one_still_answers_it() -> None:
    world = a_story_frame()
    an_attempt(world, SYNC, n=1, status="done", ended_at=EPOCH, start_sha=START)
    an_attempt(world, BUILD, n=1, start_sha=END)

    assert seen_context(world, BUILD, an_environment()).frame_start_sha == START


@pytest.mark.usefixtures("executor")
def test_a_frame_whose_attempts_recorded_no_commit_at_all_answers_nothing() -> None:
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)

    assert seen_context(world, BUILD, an_environment()).frame_start_sha is None


@pytest.mark.usefixtures("executor")
def test_a_row_outside_a_frame_has_no_frame_commit() -> None:
    world = a_world("running", EPIC_PLAN, {"checkout": "running"}, worktree_path=WORKTREE)
    an_attempt(world, "checkout", n=1, start_sha=START)
    register("git.worktree", EXECUTORS["agent"])

    assert seen_context(world, "checkout", an_environment()).frame_start_sha is None


# ── the anchors ─────────────────────────────────────────────────────────────


@pytest.mark.usefixtures("executor")
def test_the_runs_spec_folder_is_frozen_on_the_environment_the_tail_reads() -> None:
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)

    anchors = environment_of(seen_context(world, BUILD, an_environment())).anchors

    assert f"{SPEC_FOLDER}/SPEC.md" in anchors
    assert f"{SPEC_FOLDER}/stories.yaml" in anchors


@pytest.mark.usefixtures("executor")
def test_the_spec_folder_the_frames_own_row_names_is_frozen_too() -> None:
    """`initiative@1` binds one spec folder per epic, so the Run input is not the whole set."""
    world = a_world(
        "running",
        INITIATIVE_PLAN,
        {"epics[0].stories[0].build": "running"},
        {"epics[0].stories[0].build": {"spec_folder": OTHER_FOLDER}},
        worktree_path=WORKTREE,
        inputs={"initiative_folder": INITIATIVE},
    )
    an_attempt(world, "epics[0].stories[0].build", n=1)

    context = seen_context(world, "epics[0].stories[0].build", an_environment(spec_folder=None))

    assert f"{OTHER_FOLDER}/SPEC.md" in environment_of(context).anchors


@pytest.mark.usefixtures("executor")
def test_the_initiative_folders_epic_list_is_frozen() -> None:
    world = a_story_frame(inputs={"initiative_folder": INITIATIVE})
    an_attempt(world, BUILD, n=1)

    anchors = environment_of(seen_context(world, BUILD, an_environment())).anchors

    assert f"{INITIATIVE}/epics.yaml" in anchors


@pytest.mark.usefixtures("executor")
def test_the_frozen_test_set_is_the_frames_first_recorded_attempts() -> None:
    world = a_story_frame()
    an_attempt(world, SYNC, n=1, status="done", ended_at=EPOCH)
    an_attempt(world, BUILD, n=1, start_sha=START, frozen_test_files=FROZEN)
    an_attempt(world, BUILD, n=2, start_sha=END)

    anchors = environment_of(seen_context(world, BUILD, an_environment())).anchors

    assert set(FROZEN) <= anchors


@pytest.mark.usefixtures("executor")
def test_a_frame_that_recorded_no_commit_freezes_no_test_set() -> None:
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)

    anchors = environment_of(seen_context(world, BUILD, an_environment())).anchors

    assert not any(path.startswith("tests/") for path in anchors)


@pytest.mark.usefixtures("executor")
def test_an_attempt_that_recorded_a_commit_but_no_test_set_freezes_none() -> None:
    """`frozen_test_files` is `None` on every attempt that is not the frame's first."""
    world = a_story_frame()
    an_attempt(world, BUILD, n=1, start_sha=START)

    anchors = environment_of(seen_context(world, BUILD, an_environment())).anchors

    assert not any(path.startswith("tests/") for path in anchors)


# ── the frame's agent ranges, bound for the commit-guard ────────────────────


@pytest.mark.usefixtures("executor")
def test_the_commit_guard_is_handed_the_rule_bound_to_this_frame() -> None:
    world = a_story_frame()
    an_attempt(world, BUILD, n=1, start_sha=START, end_sha=END)
    an_attempt(world, "stories[0].commit-guard", n=1)

    rule = anchors_of(seen_context(world, "stories[0].commit-guard", an_environment()))

    assert rule.ranges == ((START, END),)
    assert rule.worktree == Path(WORKTREE)
    assert f"{SPEC_FOLDER}/SPEC.md" in rule.anchors


@pytest.mark.usefixtures("executor")
def test_an_attempt_that_never_came_back_contributes_no_range() -> None:
    """`end_sha` is written by the tail alone: an attempt without one bounded nothing."""
    world = a_story_frame()
    an_attempt(world, BUILD, n=1, start_sha=START)

    assert anchors_of(seen_context(world, BUILD, an_environment())).ranges == ()


@pytest.mark.usefixtures("executor")
def test_a_run_with_no_worktree_yet_binds_the_rule_to_nothing_at_all() -> None:
    world = a_world("running", EPIC_PLAN, {BUILD: "running"}, {BUILD: {}})
    an_attempt(world, BUILD, n=1)

    assert anchors_of(seen_context(world, BUILD, an_environment())).ranges == ()


@pytest.mark.usefixtures("executor")
def test_a_walker_that_resolved_no_environment_hands_the_ports_over_unchanged() -> None:
    """The one construction that cannot carry anchors: there is nowhere to put them."""
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)
    ports = ports_of(world, None)

    run_row(ports, world.run.id, world.row(BUILD).seq)

    recording = EXECUTORS["agent"]
    assert isinstance(recording, Recording)
    assert recording.seen[-1].ports is ports.step


@pytest.mark.usefixtures("executor")
def test_the_environment_the_walker_was_given_is_not_mutated() -> None:
    """`RunEnvironment` is frozen and shared across rows: the anchors are a copy's."""
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)
    environment = an_environment()

    seen_context(world, BUILD, environment)

    assert environment.anchors == frozenset()
    assert replace(environment, anchors=frozenset()) == environment


# ── a row outside a frame is given no rule at all ───────────────────────────


@pytest.mark.usefixtures("executor")
def test_a_row_outside_a_frame_is_handed_no_rule_and_no_anchors() -> None:
    """AD-17 is frame-scoped. Outside a frame there is no agent range, so all that would be
    left of the check is "anything staged named `AGENTS.md`" — which `repo-init@1`'s
    `bmad.install` row stages itself, and a Run must not park on the orchestrator's writes."""
    world = a_world("running", EPIC_PLAN, {"checkout": "running"}, worktree_path=WORKTREE)
    an_attempt(world, "checkout", n=1, start_sha=START, end_sha=END)
    register("git.worktree", EXECUTORS["agent"])

    context = seen_context(world, "checkout", an_environment())

    assert context.ports.protected_paths is None
    assert environment_of(context).anchors == frozenset()


@pytest.mark.usefixtures("executor")
def test_a_row_inside_a_frame_is_given_both() -> None:
    world = a_story_frame()
    an_attempt(world, BUILD, n=1)

    context = seen_context(world, BUILD, an_environment())

    assert isinstance(context.ports.protected_paths, FrameAnchors)
    assert environment_of(context).anchors != frozenset()


@pytest.mark.usefixtures("executor")
def test_a_row_outside_a_frame_still_gets_why_it_was_sent_back() -> None:
    """The verify failure is not frame-scoped and is resolved for that row as before."""
    world = a_world(
        "running",
        EPIC_PLAN,
        {"baseline": "running", "push": "done"},
        {"push": {"command": "make test", "on_fail": {"target_seq": 3, "max": 1}}},
        worktree_path=WORKTREE,
    )
    world.ports.steps.update(world.row("baseline").model_copy(update={"redispatch_count": 1}))
    an_attempt(world, "baseline", n=1)
    an_attempt(world, "push", n=1, status="error", exit_code=1)
    register("shell", EXECUTORS["agent"])

    failure = environment_of(seen_context(world, "baseline", an_environment())).verify_failure

    assert failure is not None
    assert failure.command == "make test"
