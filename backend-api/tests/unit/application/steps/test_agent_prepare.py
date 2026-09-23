"""Everything the `agent` kind does to a worktree before a harness sees it (AD-9, AD-14).

The order is the rule, so most of these assertions are about `FakeGit.calls` as a sequence
rather than about any one call: a prepare commit made before the WIP commit would leave the
interrupted work inside the orchestrator's own commit, and an orphan reaped after the WIP
commit would race a harness that is still writing.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.application.steps.agent import (
    CONTEXT_HEADING,
    INDEX_LOCK,
    LOCK_TIMEOUT_SECONDS,
    WHOLE_TREE,
    AgentExecutor,
)
from orchestrator.application.steps.context import (
    NO_ATTEMPT_WRITES,
    NO_HARNESS_ENV,
    NO_HARNESSES,
    NO_RUN,
    ProjectContext,
)
from orchestrator.domain.values import StepResult
from tests.unit.application.steps.agent_fixtures import (
    HEAD_SHA,
    ROW_PATH,
    SPEC_FOLDER,
    WORKTREE,
    World,
    a_world,
    an_agent_row,
    an_attempt,
    resolved,
)
from tests.unit.fakes.clock import EPOCH
from tests.unit.fakes.git import FakeGit

CONTEXT_FILE = f"{SPEC_FOLDER}/project-context.md"
#: `mark_started`, the `pgid` update and `mark_finished` — one transaction each (AD-8).
ATTEMPT_WRITES = 3
#: The worktree as the `Git` port sees it: `require_cwd` hands every call a `Path`.
WORKTREE_PATH = Path(WORKTREE)


def run(world: World) -> StepResult:
    return AgentExecutor().execute(world.ctx)


# ── orphan control ───────────────────────────────────────────────────────────


def test_an_interrupted_attempt_is_killed_the_lock_awaited_and_the_attempt_closed() -> None:
    row = an_agent_row()
    previous = an_attempt(row, 1, pgid=4242)
    world = a_world(previous=previous, git=FakeGit(status=["M src/a.py", ""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 4242}]
    closed = world.attempts.attempts[previous.id]
    assert (closed.status, closed.output_ref) == ("error", "interrupted")
    assert closed.ended_at is not None
    assert world.git.called("commit")[0][1] == "wip: story 4-1 attempt 2 (interrupted)"


def test_the_interrupted_attempt_is_closed_before_anything_is_committed() -> None:
    """AD-9's order: the orphan is reaped first, so the WIP commit is of a settled tree."""
    row = an_agent_row()
    world = a_world(
        previous=an_attempt(row, 1, pgid=4242),
        git=FakeGit(status=["M src/a.py", ""], head_sha=[HEAD_SHA]),
    )

    run(world)

    assert [name for name, _ in world.attempts.calls][:3] == ["add", "add", "mark_finished"]


def test_an_attempt_that_started_no_process_is_not_an_orphan() -> None:
    row = an_agent_row()
    world = a_world(previous=an_attempt(row, 1, pgid=None))

    run(world)

    assert world.process.called("kill_group") == []


def test_the_shape_start_attempt_leaves_behind_is_still_an_orphan() -> None:
    """The case orphan control exists for, in the exact shape it arrives in.

    `start_attempt._open_the_row` stamps `ended_at` on an attempt it finds still open after
    a restart, so an `ended_at` guard here would return early on every real orphan and kill
    nothing. `end_sha` is written only by `_finish`, and this attempt has none.
    """
    row = an_agent_row()
    previous = an_attempt(row, 1, pgid=4242, ended_at=EPOCH, status="error")
    world = a_world(previous=previous, git=FakeGit(status=[""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.process.called("kill_group") == [{"method": "kill_group", "pgid": 4242}]
    closed = world.attempts.attempts[previous.id]
    assert (closed.status, closed.output_ref) == ("error", "interrupted")


def test_an_attempt_that_came_back_is_neither_killed_nor_rewritten() -> None:
    """A retry or a verify redispatch follows a dispatch that finished; `end_sha` says so,
    and rewriting it `error` · `interrupted` would falsify the record."""
    row = an_agent_row()
    previous = an_attempt(
        row, 1, pgid=4242, ended_at=EPOCH, end_sha=HEAD_SHA, status="done", output_ref="log"
    )
    world = a_world(previous=previous, git=FakeGit(status=[""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.process.called("kill_group") == []
    unchanged = world.attempts.attempts[previous.id]
    assert (unchanged.status, unchanged.output_ref) == ("done", "log")


def test_a_first_attempt_has_nothing_to_reap() -> None:
    world = a_world()

    run(world)

    assert world.process.called("kill_group") == []


# ── the index-lock poll ──────────────────────────────────────────────────────


def test_no_lock_means_no_wait_at_all() -> None:
    row = an_agent_row()
    world = a_world(previous=an_attempt(row, 1, pgid=4242))

    run(world)

    assert world.clock.slept == []


def test_a_lock_that_clears_during_the_first_sleep_ends_the_poll() -> None:
    row = an_agent_row()
    world = a_world(previous=an_attempt(row, 1, pgid=4242), files={INDEX_LOCK: ""})
    world.clock.on_sleep = lambda: world.workspace.remove(INDEX_LOCK)

    run(world)

    assert world.clock.slept == [1.0]


def test_a_lock_that_never_clears_ends_at_the_deadline_and_the_row_proceeds() -> None:
    """Bounded, and never an exception: the row goes on and the commit reports the lock."""
    row = an_agent_row()
    world = a_world(previous=an_attempt(row, 1, pgid=4242), files={INDEX_LOCK: ""})

    result = run(world)

    assert len(world.clock.slept) == LOCK_TIMEOUT_SECONDS
    assert result.status == "done"


# ── the WIP commit ───────────────────────────────────────────────────────────


def test_a_dirty_tree_on_a_first_dispatch_is_not_committed_as_wip() -> None:
    """Operator revision, 2026-09-16: the WIP sweep is of what a *previous dispatch* left,
    so a row's first dispatch never sweeps. Its dirt is earlier rows' own writes
    (repo-init's `bmad.install` leaves the method for the Template's `commit` step), and
    staging it whole as `(interrupted)` stole that step's commit. Replaces the assertion
    that any dirty tree was staged whole and committed as WIP; the re-dispatch cases below
    and under orphan control keep theirs."""
    world = a_world(git=FakeGit(status=["?? notes.md", ""], head_sha=[HEAD_SHA]))

    run(world)

    assert (WORKTREE_PATH, None) not in world.git.called("stage")
    assert all("(interrupted)" not in message for _, message in world.git.called("commit"))


def test_a_finished_previous_attempts_dirt_is_still_swept_as_wip() -> None:
    """A re-dispatch sweeps whatever the last dispatch left, finished or not (Operator
    revision, 2026-09-16): the answer archive stages the story file's old path, which
    only stages as a deletion when the file is tracked — the sweep is what tracks it."""
    row = an_agent_row()
    previous = an_attempt(
        row, 1, pgid=4242, ended_at=EPOCH, end_sha=HEAD_SHA, status="done", output_ref="log"
    )
    world = a_world(previous=previous, git=FakeGit(status=["?? notes.md", ""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.git.called("stage")[0] == (WORKTREE_PATH, None)
    assert world.git.called("commit")[0][1] == "wip: story 4-1 attempt 2 (interrupted)"


def test_a_clean_worktree_leaves_no_wip_commit() -> None:
    world = a_world(git=FakeGit(status=["   \n  "], head_sha=[HEAD_SHA]))

    run(world)

    assert world.git.called("commit") == []


# ── the context document and the prepare commit ──────────────────────────────


def context_world(**over: object) -> World:
    project = ProjectContext(
        context_text="ctx",
        context_paths=("a.md", "gone.md"),
    )
    return a_world(project=project, files={"a.md": "# a"}, **over)  # type: ignore[arg-type]


def test_the_context_document_holds_the_text_and_only_the_paths_that_are_there() -> None:
    world = context_world(git=FakeGit(status=["", " M x", ""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.workspace.read(CONTEXT_FILE) == f"ctx\n\n{CONTEXT_HEADING}\n\n- a.md\n"


def test_a_context_path_the_worktree_does_not_hold_is_left_out_and_never_raises() -> None:
    world = context_world(git=FakeGit(status=["", " M x", ""], head_sha=[HEAD_SHA]))

    result = run(world)

    assert "gone.md" not in (world.workspace.read(CONTEXT_FILE) or "")
    assert result.status == "done"


def test_the_prepare_commit_stages_exactly_the_document_it_wrote() -> None:
    # First dispatch: the WIP check reads no status (Operator revision, 2026-09-16), so
    # the first scripted answer is the one the prepare commit's own staging check reads.
    world = context_world(git=FakeGit(status=[f"A  {CONTEXT_FILE}", ""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.git.called("stage") == [(WORKTREE_PATH, CONTEXT_FILE)]
    assert world.git.called("commit") == [
        (WORKTREE_PATH, "orchestrator: prepare story 4-1 attempt 1")
    ]


def test_an_unchanged_document_is_staged_and_then_not_committed() -> None:
    """`status` after the staging is empty when the same bytes are already committed."""
    world = context_world(git=FakeGit(status=[""], head_sha=[HEAD_SHA]))

    run(world)

    assert world.git.called("stage") == [(WORKTREE_PATH, CONTEXT_FILE)]
    assert world.git.called("commit") == []


def test_unrelated_worktree_dirt_does_not_trigger_a_commit_of_nothing() -> None:
    """Production incident, 2026-09-22 (Operator report): a harness's own uncommitted work
    left the worktree dirty on a path this row never touched, and the check this replaces —
    "is the worktree dirty at all" — read that as something to commit even though the one
    target it staged (the context document) was already the committed text, so `stage` was a
    no-op. `git commit` then failed on an empty index — `nothing added to commit but
    untracked files present` — surfaced to the Operator as `internal: GitError`, unchanged on
    retry since nothing about the worktree state ever changed between attempts."""
    world = context_world(git=FakeGit(status=["?? somewhere/else.md"], head_sha=[HEAD_SHA]))

    run(world)

    assert world.git.called("stage") == [(WORKTREE_PATH, CONTEXT_FILE)]
    assert world.git.called("commit") == []


def test_a_row_with_no_spec_folder_writes_nothing_and_commits_nothing() -> None:
    world = a_world(
        with_resolved=resolved(spec_folder=""),
        project=ProjectContext(context_text="ctx"),
        git=FakeGit(status=[""], head_sha=[HEAD_SHA]),
    )

    run(world)

    assert world.workspace.tree() == ()
    assert world.git.called("stage") == []
    assert world.git.called("commit") == []


# ── mark_started ─────────────────────────────────────────────────────────────


def test_the_start_half_records_the_head_the_orchestrator_left_and_no_group() -> None:
    world = a_world(git=FakeGit(status=[""], head_sha=[HEAD_SHA]))

    run(world)

    started = world.attempts.attempts[world.attempt.id]
    assert started.start_sha == HEAD_SHA
    assert started.harness == "claude"
    assert started.model == "claude-opus-5"


def test_the_start_half_commits_in_a_unit_of_work_of_its_own() -> None:
    world = a_world()

    run(world)

    assert [name for name, _ in world.attempts.calls if name == "mark_started"] == ["mark_started"]
    assert all(uow.committed for uow in world.uows)
    assert len(world.uows) == ATTEMPT_WRITES


def test_a_row_that_bound_no_model_records_none_rather_than_an_empty_string() -> None:
    world = a_world(with_resolved=resolved(model=""))

    run(world)

    assert world.attempts.attempts[world.attempt.id].model is None


# ── the frozen test set ──────────────────────────────────────────────────────


def a_tree(*paths: str, **over: object) -> World:
    """A world whose committed tree at `start_sha` holds exactly `paths`."""
    return a_world(
        test_globs=("tests/**", "**/*.test.*"),
        git=FakeGit(status=[""], head_sha=[HEAD_SHA], list_files=[paths]),
        **over,  # type: ignore[arg-type]
    )


def test_the_frames_first_attempt_freezes_the_test_files_the_globs_name() -> None:
    world = a_tree("tests/a.py", "src/b.py", "src/x.test.ts")

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files == (
        "src/x.test.ts",
        "tests/a.py",
    )


def test_the_set_is_read_out_of_the_committed_tree_at_the_start_sha() -> None:
    """AD-17 and 5.6: the anchors must come from the same object store the agent range is
    computed against, never from the live worktree — `git.status` there is untracked noise.

    The pathspec is asserted because the obvious spelling is wrong: `git ls-tree -- ""`
    refuses with "empty string is not a valid pathspec", and `SubprocessGit.list_files`
    reports a refusal as `()` — so `""` here would freeze an empty set on every Run and
    nothing would fail.
    """
    world = a_tree("tests/a.py")

    run(world)

    assert world.git.called("list_files") == [(Path(WORKTREE), HEAD_SHA, WHOLE_TREE)]
    assert WHOLE_TREE == "."


def test_a_worktree_with_no_commit_yet_freezes_nothing() -> None:
    world = a_world(test_globs=("tests/**",), git=FakeGit(status=[""], head_sha=[None]))

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files is None


def test_a_later_attempt_freezes_nothing_because_the_first_one_already_did() -> None:
    row = an_agent_row()
    world = a_tree("tests/a.py", previous=an_attempt(row, 1, start_sha=HEAD_SHA))

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files is None


def test_an_attempt_after_one_that_never_reached_a_start_sha_still_freezes() -> None:
    """A first attempt that parked in prepare recorded no anchors; if the second skipped
    too, AD-17's set would be `None` for the whole row and the rule would protect nothing."""
    row = an_agent_row()
    world = a_tree("tests/a.py", previous=an_attempt(row, 1, start_sha=None))

    run(world)

    assert world.attempts.attempts[world.attempt.id].frozen_test_files == ("tests/a.py",)


# ── the misconfigured row ────────────────────────────────────────────────────


def test_a_row_naming_a_harness_this_instance_does_not_have_parks_before_anything() -> None:
    world = a_world(with_resolved=resolved(harness="nope"))

    result = run(world)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == "harness misconfigured: unknown harness nope"
    assert result.park.path == ROW_PATH
    assert world.git.called("commit") == []
    assert world.uows == []


# ── the wiring bugs ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("port", "message"),
    [
        ("harnesses", NO_HARNESSES),
        ("harness_env", NO_HARNESS_ENV),
        ("attempt_writes", NO_ATTEMPT_WRITES),
    ],
)
def test_an_unwired_port_is_reported_as_the_field_it_is(port: str, message: str) -> None:
    """`steps/registry.py` turns this into `internal: RuntimeError` and parks the Run."""
    world = a_world()
    ctx = replace(world.ctx, ports=replace(world.ctx.ports, **{port: None}))

    with pytest.raises(RuntimeError, match=message):
        AgentExecutor().execute(ctx)


def test_a_run_environment_that_carries_no_run_is_reported_the_same_way() -> None:
    world = a_world()
    env = world.ctx.ports.run_env
    assert env is not None
    ctx = replace(world.ctx, ports=replace(world.ctx.ports, run_env=replace(env, run=None)))

    with pytest.raises(RuntimeError, match=NO_RUN):
        AgentExecutor().execute(ctx)
