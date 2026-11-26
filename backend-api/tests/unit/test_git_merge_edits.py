"""`application/steps/git_merge_edits.py`: AD-17 over the merge agent's edits before a
`git.merge` row resumes (story 8.4; Operator ruling 2026-11-26)."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from orchestrator.application.rules.protected_paths import HITS_KEY
from orchestrator.application.steps.git_merge import FROM_KEY, KIND, GitMergeExecutor
from orchestrator.application.steps.git_merge_edits import EDITS_HEADING, agent_edits, protected
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from orchestrator.domain.values import StepResult
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import WORKTREE, a_context, a_row, a_worktree, an_environment

FROM_BRANCH = "feat/epic-1"
SPEC = "initiatives/i/epic-1/SPEC.md"
TEST = "tests/unit/test_x.py"
RESOLVED_SHA = "feed0123456789abcdefbeef0123456789abcdef"
DIFF = "@@ -1 +1 @@\n-a\n+b\n"


def a_merge_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={FROM_KEY: FROM_BRANCH, "timeout_min": 5}, path="merge")


def a_ctx(git: FakeGit, resume: str | None = "continue", **env: Any):  # type: ignore[no-untyped-def]
    environment = an_environment(worktrees=(a_worktree(),), **env)
    return a_context(a_merge_row(), git=git, env=environment, resume=resume)  # type: ignore[arg-type]


def execute(git: FakeGit, resume: str | None = "continue", **env: Any) -> StepResult:
    return GitMergeExecutor().execute(a_ctx(git, resume, **env))


def names(git: FakeGit) -> list[str]:
    return [name for name, _ in git.calls]


def hit_paths(result: StepResult) -> list[str]:
    return [entry["path"] for entry in result.payload[HITS_KEY]]


def test_an_agent_edit_to_an_anchor_parks_protected_path_and_commits_nothing() -> None:
    git = FakeGit(merge_in_progress=[True], status=[f"M  {SPEC}"], diff=[DIFF, DIFF])

    result = execute(git)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.reason == f"protected path modified: {SPEC}"
    assert result.output_ref == f"{EDITS_HEADING}\n{SPEC}"
    assert hit_paths(result) == [SPEC]
    assert not {"stage", "commit", "merge"} & set(names(git))
    assert [call[1] for call in git.called("diff")] == ["HEAD", "MERGE_HEAD"]


def test_an_anchor_equal_to_merge_heads_version_is_not_a_hit() -> None:
    git = FakeGit(
        merge_in_progress=[True], status=[f"M  {SPEC}"], diff=[DIFF, ""], commit=[RESOLVED_SHA]
    )

    result = execute(git)

    assert result.status == "done"
    assert result.park is None
    assert result.output_ref == RESOLVED_SHA
    assert len(git.called("commit")) == 1


def test_an_anchor_equal_to_heads_version_is_not_read_against_merge_head() -> None:
    git = FakeGit(merge_in_progress=[True], status=[f" M {SPEC}"], diff=[""])

    assert agent_edits(a_ctx(git), WORKTREE) == ()  # type: ignore[arg-type]
    assert [call[1] for call in git.called("diff")] == ["HEAD"]


def test_an_untracked_agents_md_is_new_in_neither_side_and_a_hit() -> None:
    git = FakeGit(merge_in_progress=[True], status=["?? docs/AGENTS.md"])

    result = execute(git)

    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert hit_paths(result) == ["docs/AGENTS.md"]
    assert git.called("diff") == []


def test_an_edit_to_an_existing_test_is_a_hit_and_a_new_test_is_not() -> None:
    status = f" M {TEST}\nA  tests/unit/test_new.py"
    git = FakeGit(merge_in_progress=[True], status=[status], diff=[DIFF])

    result = execute(git, test_globs=("tests/**/test_*.py",))

    assert result.park is not None
    assert hit_paths(result) == [TEST]


def test_a_frame_anchor_is_a_hit_whatever_its_name() -> None:
    git = FakeGit(merge_in_progress=[True], status=[" M notes/frozen.txt"], diff=[DIFF])

    result = execute(git, anchors=frozenset({"notes/frozen.txt"}))

    assert result.park is not None
    assert hit_paths(result) == ["notes/frozen.txt"]


def test_an_accepted_edit_lets_the_resume_commit_it() -> None:
    git = FakeGit(
        merge_in_progress=[True], status=[f"M  {SPEC}"], diff=[DIFF, DIFF], commit=[RESOLVED_SHA]
    )

    result = execute(git, accepted_paths=(SPEC,))

    assert result.status == "done"
    assert result.output_ref == RESOLVED_SHA


def test_unmerged_paths_are_not_the_agents_edits() -> None:
    git = FakeGit(merge_in_progress=[True], status=[f"UU {SPEC}\nAA b/AGENTS.md"])

    assert agent_edits(a_ctx(git), WORKTREE) == ()  # type: ignore[arg-type]
    assert git.called("diff") == []


def test_a_non_anchor_edit_is_returned_but_parks_nothing() -> None:
    git = FakeGit(merge_in_progress=[True], status=[" M src/a.py"], diff=[DIFF, DIFF])

    ctx = a_ctx(git)

    assert protected(ctx, WORKTREE) is None  # type: ignore[arg-type]
    assert agent_edits(a_ctx(FakeGit(status=[" M src/a.py"], diff=[DIFF])), WORKTREE) == (  # type: ignore[arg-type]
        Change(path="src/a.py", kind="modified"),
    )


def test_a_retry_checks_the_edits_before_the_abort() -> None:
    git = FakeGit(merge_in_progress=[True], status=[f"M  {SPEC}"], diff=[DIFF, DIFF])

    result = execute(git, resume="retry")

    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert git.called("merge") == []


def test_a_retry_answering_this_park_aborts_and_re_runs_the_merge() -> None:
    git = FakeGit(merge_in_progress=[True], status=[f"M  {SPEC}"], merge=[RESOLVED_SHA])
    previous = Attempt(
        id=new_id(),
        run_id=new_id(),
        step_run_id=new_id(),
        n=3,
        status="error",
        output_ref=f"{EDITS_HEADING}\n{SPEC}",
    )
    ctx = replace(a_ctx(git, resume="retry"), previous_attempt=previous)

    result = GitMergeExecutor().execute(ctx)

    assert result.status == "done"
    assert len(git.called("merge")) == 1
    assert git.called("diff") == []


def test_a_retry_with_no_merge_in_progress_re_runs_the_merge() -> None:
    git = FakeGit(merge=[RESOLVED_SHA])

    result = execute(git, resume="retry")

    assert result.output_ref == RESOLVED_SHA
    assert len(git.called("merge")) == 1
    assert "status" not in names(git)


def test_a_first_run_and_another_resume_read_nothing() -> None:
    for resume in (None, "skip_step"):
        git = FakeGit(merge_in_progress=[True])

        assert protected(a_ctx(git, resume=resume), WORKTREE) is None  # type: ignore[arg-type]
        assert git.calls == []
