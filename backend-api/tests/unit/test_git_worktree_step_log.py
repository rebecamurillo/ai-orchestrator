"""`git.worktree` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.git_worktree import KIND, GitWorktreeExecutor
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import (
    BRANCH,
    DEFAULT_BRANCH,
    a_context,
    a_row,
    an_environment,
    without,
)


def a_worktree_context(git: FakeGit | None = None, **env: object) -> StepContext:
    row = a_row(
        kind=KIND, with_resolved={"base": DEFAULT_BRANCH, "branch": BRANCH, "timeout_min": 5}
    )
    return a_context(row, git=git, env=an_environment(**env))


def test_a_fresh_worktree_logs_each_git_call_in_order() -> None:
    git = FakeGit()
    ctx = a_worktree_context(git)

    result = GitWorktreeExecutor().execute(ctx)

    assert result.status == "done"
    assert result.log_path == str(log_path(ctx))
    writes = ctx.ports.step_log.writes  # type: ignore[union-attr]
    assert len(writes) == 1
    lines = writes[0][3]
    assert [line.split()[1] for line in lines if line.startswith("> ")] == [
        call[0] for call in git.calls
    ]
    assert not [line for line in lines if line.startswith("refs updated:")]


def test_a_held_worktree_parks_with_an_empty_log_and_a_path() -> None:
    ctx = a_worktree_context(held_by_label="run-9")

    result = GitWorktreeExecutor().execute(ctx)

    assert result.park is not None
    assert result.log_path == str(log_path(ctx))
    assert ctx.ports.step_log.writes[0][3] == ()  # type: ignore[union-attr]


def test_every_outcome_carries_the_log_and_keeps_its_fields() -> None:
    failed = GitError(command="git clone", exit_code=128, output="denied")
    for script in ({}, {"clone_base": [failed]}, {"worktree_add": [failed]}):
        ctx = a_worktree_context(FakeGit(**script))  # type: ignore[arg-type]
        bare = without(a_worktree_context(FakeGit(**script)), step_log=None)  # type: ignore[arg-type]

        result = GitWorktreeExecutor().execute(ctx)
        plain = GitWorktreeExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
