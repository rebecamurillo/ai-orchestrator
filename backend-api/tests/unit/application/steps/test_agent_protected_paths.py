"""AD-17's two executor call sites: the agent tail's own range, and the commit-guard's union.

The rule itself is `tests/unit/application/test_protected_paths_rule.py`'s, over no ports at
all. What is asserted here is the wiring only an executor can settle:

- the check runs **before** the routing (FR-31), so a modified anchor wins over whatever the
  Story file says and the liveness glob is never even asked;
- the range is *this attempt's* — `start_sha..end_sha` unioned with what it left uncommitted
  — so an operator commit between two attempts is outside it by construction;
- a hit is `error` + `park: protected_path`, the reason names the files, and the result
  carries the hit list as its payload for the gate record (AD-8 writes it, not the executor);
- `run.accepted_paths` excludes a path from every later check in the same frame (AD-9);
- a `continue` carrying files dispatches **nothing**: the work is already in the worktree,
  so the executor re-runs the tail over the previous attempt and routes on the file.

The commit-guard's own union is the last section: `git_commit.py` is unchanged by this
story, and what changed is that the port it already called now answers.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from orchestrator.application.rules.protected_paths import FrameAnchors
from orchestrator.application.steps.agent import AgentExecutor
from orchestrator.application.steps.agent_tail import PROTECTED
from orchestrator.application.steps.git_commit import (
    KIND,
    GitCommitExecutor,
)
from orchestrator.application.steps.git_commit import (
    PROTECTED as COMMIT_PROTECTED,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.git import Change
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    WORKTREE,
    World,
    a_gate_record,
    an_agent_row,
    an_attempt,
)
from tests.unit.application.steps.agent_tail_fixtures import (
    END_SHA,
    LOG_PATH,
    STORY_GLOB,
    a_tail_world,
)
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.step_fixtures import a_context, a_row, an_environment

WORKTREE_PATH = Path(WORKTREE)
SPEC_FOLDER = "specs/notifications"
SPEC_MD = f"{SPEC_FOLDER}/SPEC.md"
STORIES_YAML = f"{SPEC_FOLDER}/stories.yaml"
FROZEN_TEST = "tests/a.py"
NEW_TEST = "tests/new.py"
ANCHORS = frozenset({SPEC_MD, STORIES_YAML, FROZEN_TEST})


def a_git(*changes: Change, status: str = "") -> FakeGit:
    """The dispatch's own two SHAs, the range it reports, and the tree it left behind."""
    return FakeGit(
        status=[status],
        head_sha=[HEAD_SHA, END_SHA],
        diff_changes=[tuple(changes)],
    )


def a_protected_world(*, accepted: tuple[str, ...] = (), **over: Any) -> World:
    """A tail world whose walker resolved AD-17's anchors onto the Run's environment."""
    world = a_tail_world(**over)
    environment = world.ctx.ports.run_env
    assert environment is not None
    world.ctx = replace(
        world.ctx,
        ports=replace(
            world.ctx.ports,
            run_env=replace(environment, anchors=ANCHORS, accepted_paths=accepted),
        ),
    )
    return world


def a_previous(**over: Any) -> Attempt:
    """The attempt the `protected_path` park was raised on: it started, ran and came back."""
    fields: dict[str, Any] = {
        "status": "error",
        "start_sha": HEAD_SHA,
        "end_sha": END_SHA,
        "log_path": str(LOG_PATH),
        "session_id": "s-1",
    }
    fields.update(over)
    return an_attempt(an_agent_row(), 1, **fields)


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


# ── a hit, and what it stops ────────────────────────────────────────────────


def test_an_anchor_the_attempts_range_modified_parks_the_run() -> None:
    world = a_protected_world(git=a_git(Change(path=SPEC_MD, kind="modified")))

    result = run(world)

    assert result.status == "error"
    assert result.gate == "liveness"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == PROTECTED.format(paths=SPEC_MD)


def test_the_hit_list_travels_on_the_result_for_the_gate_record() -> None:
    """AD-17 records which files were touched, so 5.9's trajectory can carry them."""
    world = a_protected_world(git=a_git(Change(path=SPEC_MD, kind="modified")))

    result = run(world)

    assert result.payload == {"hits": [{"path": SPEC_MD, "kind": "modified"}]}


def test_the_range_is_the_attempts_own_two_commits() -> None:
    world = a_protected_world(git=a_git())

    run(world)

    assert world.git.called("diff_changes") == [(WORKTREE_PATH, HEAD_SHA, END_SHA)]


def test_the_story_file_glob_is_never_asked_when_an_anchor_was_touched() -> None:
    """FR-31: a modified anchor wins over every route, which it cannot do from behind one."""
    world = a_protected_world(git=a_git(Change(path=SPEC_MD, kind="modified")))

    run(world)

    assert STORY_GLOB not in world.workspace.globbed


def test_an_agents_file_created_anywhere_is_a_hit() -> None:
    """It is not in the anchor set and cannot be: creating one is the case AD-17 names."""
    world = a_protected_world(git=a_git(status="?? web-client/AGENTS.md\n"))

    result = run(world)

    assert result.payload == {"hits": [{"path": "web-client/AGENTS.md", "kind": "added"}]}


def test_a_frozen_test_file_deleted_is_a_hit_that_says_deleted() -> None:
    world = a_protected_world(git=a_git(Change(path=FROZEN_TEST, kind="deleted")))

    result = run(world)

    assert result.payload == {"hits": [{"path": FROZEN_TEST, "kind": "deleted"}]}


def test_only_the_frozen_test_file_is_a_hit_when_a_new_one_is_added_beside_it() -> None:
    world = a_protected_world(
        git=a_git(Change(path=FROZEN_TEST, kind="modified"), Change(path=NEW_TEST, kind="added"))
    )

    result = run(world)

    assert result.reason == PROTECTED.format(paths=FROZEN_TEST)


def test_what_the_attempt_left_uncommitted_is_checked_with_its_commits() -> None:
    world = a_protected_world(git=a_git(status=f" M {STORIES_YAML}\n"))

    result = run(world)

    assert result.reason == PROTECTED.format(paths=STORIES_YAML)


# ── what is not a hit ───────────────────────────────────────────────────────


def test_a_file_the_agent_created_inside_the_frame_is_editable_on_a_later_attempt() -> None:
    world = a_protected_world(git=a_git(Change(path=NEW_TEST, kind="modified")))

    assert run(world) == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


def test_an_operator_edit_between_two_attempts_is_outside_the_range() -> None:
    """The commit is not in `start_sha..end_sha` and the tree is clean of it: no hit at all."""
    world = a_protected_world(git=a_git())

    result = run(world)

    assert result.park is None
    assert result.status == "done"


def test_an_accepted_path_is_not_a_hit_a_second_time() -> None:
    world = a_protected_world(accepted=(SPEC_MD,), git=a_git(Change(path=SPEC_MD, kind="modified")))

    result = run(world)

    assert result.park is None
    assert result.status == "done"


def test_an_attempt_that_recorded_no_commits_asks_git_for_no_range() -> None:
    """A worktree with no commit yet: there is no range to diff, and the tree still counts."""
    world = a_protected_world(git=FakeGit(status=[""], head_sha=[None]))

    result = run(world)

    assert world.git.called("diff_changes") == []
    assert result.status == "done"


def test_a_run_whose_walker_resolved_no_anchors_routes_exactly_as_before() -> None:
    """Every `RunEnvironment(...)` written before this story carries an empty anchor set."""
    world = a_tail_world(git=a_git(Change(path=SPEC_MD, kind="modified")))

    assert run(world) == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


# ── the Accept branch (AD-9: a `continue` on `protected_path`) ──────────────


def accepting(*changes: Change) -> World:
    """The row as the walker hands it back after the Operator accepted the files."""
    row = an_agent_row()
    return a_protected_world(
        accepted=(SPEC_MD,),
        previous=a_previous(),
        resume=a_gate_record(row, "continue", {"files": [SPEC_MD]}),
        git=a_git(*(changes or (Change(path=SPEC_MD, kind="modified"),))),
    )


def test_an_accepted_continue_dispatches_no_harness_at_all() -> None:
    world = accepting()

    run(world)

    assert world.harness.calls == []


def test_an_accepted_continue_makes_no_wip_and_no_prepare_commit() -> None:
    world = accepting()

    run(world)

    assert world.git.called("commit") == []


def test_an_accepted_continue_re_checks_the_previous_attempts_range() -> None:
    world = accepting()

    run(world)

    assert world.git.called("diff_changes") == [(WORKTREE_PATH, HEAD_SHA, END_SHA)]


def test_an_accepted_continue_routes_on_the_story_file_with_the_files_excluded() -> None:
    world = accepting()

    assert run(world) == StepResult(status="done", gate="liveness", output_ref=str(LOG_PATH))


def test_an_accepted_continue_still_parks_on_an_anchor_nobody_accepted() -> None:
    world = accepting(Change(path=STORIES_YAML, kind="modified"))

    result = run(world)

    assert result.reason == PROTECTED.format(paths=STORIES_YAML)


def test_a_continue_carrying_no_files_is_an_ordinary_dispatch() -> None:
    """A `continue` on a `checkpoint` park carries none, and that row must run again."""
    row = an_agent_row()
    world = a_protected_world(
        previous=a_previous(), resume=a_gate_record(row, "continue"), git=a_git()
    )

    run(world)

    assert [call["method"] for call in world.harness.calls] == ["start", "wait"]


def test_a_continue_on_a_rows_first_attempt_is_an_ordinary_dispatch() -> None:
    """There is no previous range to re-check, so there is nothing to re-run over."""
    row = an_agent_row()
    world = a_protected_world(
        resume=a_gate_record(row, "continue", {"files": [SPEC_MD]}), git=a_git()
    )

    run(world)

    assert [call["method"] for call in world.harness.calls] == ["start", "wait"]


def test_another_signal_entirely_is_an_ordinary_dispatch() -> None:
    row = an_agent_row()
    world = a_protected_world(
        previous=a_previous(), resume=a_gate_record(row, "retry"), git=a_git()
    )

    run(world)

    assert [call["method"] for call in world.harness.calls] == ["start", "wait"]


# ── the commit-guard, over the same rule ────────────────────────────────────


def test_the_commit_guard_parks_on_an_uncommitted_anchor_and_commits_nothing() -> None:
    """AD-17's second call site, through the port `git_commit.py` already called."""
    git = FakeGit(status=[f" M {STORIES_YAML}\n"])
    context = a_context(
        a_row(kind=KIND, with_resolved={"message": "story 5-6 (orchestrator)"}),
        git=git,
        protected_paths=FrameAnchors(git=git, worktree=WORKTREE_PATH, anchors=ANCHORS),
        env=an_environment(spec_folder=SPEC_FOLDER),
    )

    result = GitCommitExecutor().execute(context)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == COMMIT_PROTECTED.format(paths=STORIES_YAML)
    assert git.called("commit") == []


def test_the_commit_guard_sees_an_anchor_an_earlier_attempt_of_the_frame_committed() -> None:
    """The tree is clean of it now; the frame's recorded agent range is not (AD-17)."""
    git = FakeGit(
        status=[" M src/thing.py\n"],
        diff_changes=[(Change(path=SPEC_MD, kind="modified"),)],
    )
    context = a_context(
        a_row(kind=KIND, with_resolved={"message": "story 5-6 (orchestrator)"}),
        git=git,
        protected_paths=FrameAnchors(
            git=git,
            worktree=WORKTREE_PATH,
            anchors=ANCHORS,
            ranges=((HEAD_SHA, END_SHA),),
        ),
        env=an_environment(spec_folder=SPEC_FOLDER),
    )

    result = GitCommitExecutor().execute(context)

    assert result.reason == COMMIT_PROTECTED.format(paths=SPEC_MD)
    assert git.called("commit") == []


# ── the timeout park is checked too ─────────────────────────────────────────


def a_timed_out_world(*changes: Change) -> World:
    """A dispatch the deadline killed, over a range that touched `changes`."""
    harness = FakeHarness()
    harness.results.append(
        HarnessResult(session_id="s-1", exit_code=None, timed_out=True, log_path=LOG_PATH)
    )
    return a_protected_world(harness=harness, git=a_git(*changes))


def test_a_dispatch_that_edited_an_anchor_and_then_hung_parks_on_the_anchor() -> None:
    """The timeout park returns without routing, so a check behind it would never run — and
    the edit would then be committed by attempt 2's WIP commit, inside no agent range."""
    world = a_timed_out_world(Change(path=SPEC_MD, kind="modified"))

    result = run(world)

    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == PROTECTED.format(paths=SPEC_MD)
    assert result.output_ref == str(LOG_PATH)


def test_a_dispatch_that_hung_and_touched_nothing_still_parks_on_the_timeout() -> None:
    world = a_timed_out_world()

    result = run(world)

    assert result.park is not None
    assert result.park.kind == "timeout"


# ── how several hits read ───────────────────────────────────────────────────


def test_several_hits_are_one_sentence_and_one_ordered_payload() -> None:
    world = a_protected_world(
        git=a_git(Change(path=STORIES_YAML, kind="modified"), Change(path=SPEC_MD, kind="deleted"))
    )

    result = run(world)

    assert result.reason == PROTECTED.format(paths=f"{STORIES_YAML}, {SPEC_MD}")
    assert result.payload == {
        "hits": [
            {"path": STORIES_YAML, "kind": "modified"},
            {"path": SPEC_MD, "kind": "deleted"},
        ]
    }


# ── a staged rename at the commit-guard ─────────────────────────────────────


def test_the_commit_guard_refuses_a_staged_rename_of_an_anchor() -> None:
    """Porcelain writes one line and `git_commit.py` keeps its remainder, so the rule is
    handed `old -> new` as a single string with the rename letter already stripped."""
    git = FakeGit(status=[f"R  {SPEC_MD} -> {SPEC_FOLDER}/OLD.md\n"])
    context = a_context(
        a_row(kind=KIND, with_resolved={"message": "story 5-6 (orchestrator)"}),
        git=git,
        protected_paths=FrameAnchors(git=git, worktree=WORKTREE_PATH, anchors=ANCHORS),
        env=an_environment(spec_folder=SPEC_FOLDER),
    )

    result = GitCommitExecutor().execute(context)

    assert result.reason == COMMIT_PROTECTED.format(paths=SPEC_MD)
    assert git.called("commit") == []
