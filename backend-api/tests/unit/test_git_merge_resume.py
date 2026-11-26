"""`application/steps/git_merge.py` resumed by `continue` (story 8.4, 2026-11-25).

The merge agent's conversation ends with the machine's `continue`; the executor then keeps
what the agent did. `retry` stays the row re-run whole.
"""

from __future__ import annotations

from orchestrator.application.rules.merge_conflicts import CONFLICTED_HEADING
from orchestrator.application.steps.git_merge import (
    ALREADY_MERGED,
    CONFLICT,
    FROM_KEY,
    KIND,
    GitMergeExecutor,
)
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import BRANCH, a_context, a_row, a_worktree, an_environment

FROM_BRANCH = "feat/epic-1"
RESOLVED_SHA = "feed0123456789abcdefbeef0123456789abcdef"
NEXT_SHA = "beef0123456789abcdefbeef0123456789abcdef"


def a_merge_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={FROM_KEY: FROM_BRANCH, "timeout_min": 5}, path="merge")


def run(git: FakeGit, resume: str | None = "continue"):  # type: ignore[no-untyped-def]
    env = an_environment(worktrees=(a_worktree(),))
    ctx = a_context(a_merge_row(), git=git, env=env, resume=resume)  # type: ignore[arg-type]
    return GitMergeExecutor().execute(ctx)


def names(git: FakeGit) -> list[str]:
    return [name for name, _ in git.calls]


def test_continue_with_no_unmerged_path_and_no_merge_in_progress_runs_the_merge() -> None:
    git = FakeGit(status=[" M a.md\n?? b.md"], merge=[None])

    result = run(git)

    assert result.status == "done"
    assert result.reason == ALREADY_MERGED
    assert result.park is None
    assert "merge" in names(git)


def test_continue_with_no_unmerged_path_merges_what_remains() -> None:
    git = FakeGit(merge=[NEXT_SHA])

    result = run(git)

    assert result.status == "done"
    assert result.output_ref == NEXT_SHA


def test_continue_with_an_unmerged_path_re_parks_and_touches_nothing() -> None:
    git = FakeGit(status=["UU a.md\nAA b.md\n?? c.md"])

    result = run(git)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "merge_conflict"
    assert result.reason == CONFLICT.format(**{FROM_KEY: FROM_BRANCH, "branch": BRANCH})
    assert result.output_ref == f"{CONFLICTED_HEADING}\na.md\nb.md"
    assert not {"merge", "commit", "stage"} & set(names(git))


def test_continue_with_a_merge_in_progress_commits_what_the_agent_resolved() -> None:
    git = FakeGit(merge_in_progress=[True], commit=[RESOLVED_SHA])

    result = run(git)

    assert result.status == "done"
    assert result.output_ref == RESOLVED_SHA
    assert "merge" not in names(git)
    assert names(git).index("stage") < names(git).index("commit")
    message = git.called("commit")[0][1]
    assert message == f"merge: {FROM_BRANCH} into {BRANCH} (orchestrator)"


def test_retry_with_no_merge_open_runs_the_merge_whole_and_never_reads_the_status() -> None:
    """Operator ruling 2026-11-26: a `retry` first asks whether a merge is open, for the
    agent-edit check (`test_git_merge_edits.py`); with none it is today's whole re-run."""
    git = FakeGit(merge=[NEXT_SHA])

    result = run(git, resume="retry")

    assert result.output_ref == NEXT_SHA
    assert names(git).count("merge") == 1
    assert "status" not in names(git)
    assert names(git)[0] == "merge_in_progress"
