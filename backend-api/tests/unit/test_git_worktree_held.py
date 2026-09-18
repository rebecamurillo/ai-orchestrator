"""`GitWorktreeExecutor` backstop: the `held_by_label` race guard (story 5-1, AD-14).

When another Run holds the same (repository, branch) partition and `env.held_by_label`
is set, `execute` must return a `StepResult(status="error", park.kind="misconfigured")`
with the branch-held reason, without touching git or the workspace.

When `held_by_label` is `None`, the executor proceeds normally.
"""

from __future__ import annotations

from orchestrator.application.steps.git_worktree import HELD_BY, KIND, GitWorktreeExecutor
from orchestrator.domain.values import StepResult
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import (
    DEFAULT_BRANCH,
    a_context,
    a_row,
    an_environment,
)

BRANCH = "feat/s"
HOLDER_LABEL = "epic · feat/s"
RESOLVED = {"base": DEFAULT_BRANCH, "branch": BRANCH, "timeout_min": 5}


def a_worktree_row() -> object:
    return a_row(kind=KIND, with_resolved=dict(RESOLVED))


# ── held_by_label set → backstop error ───────────────────────────────────────


def test_execute_returns_error_when_held_by_label_is_set() -> None:
    """When env.held_by_label is set, execute returns error/misconfigured immediately."""
    env = an_environment(held_by_label=HOLDER_LABEL)
    row = a_worktree_row()
    ctx = a_context(row, env=env, git=FakeGit())  # type: ignore[arg-type]

    result = GitWorktreeExecutor().execute(ctx)

    assert isinstance(result, StepResult)
    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    expected_reason = HELD_BY.format(run=HOLDER_LABEL)
    assert result.reason == expected_reason
    assert result.park.reason == expected_reason


def test_execute_does_not_touch_git_when_held_by_label_is_set() -> None:
    """The backstop returns before any git call, so no clone/fetch/worktree-add happens."""
    git = FakeGit(base_exists=[True], branch_exists=[False])
    env = an_environment(held_by_label=HOLDER_LABEL)
    row = a_worktree_row()
    ctx = a_context(row, env=env, git=git)  # type: ignore[arg-type]

    GitWorktreeExecutor().execute(ctx)

    assert git.called("clone_base") == []
    assert git.called("fetch_base") == []
    assert git.called("worktree_add") == []


# ── held_by_label is None → normal execution path ────────────────────────────


def test_execute_proceeds_normally_when_held_by_label_is_none() -> None:
    """When held_by_label is None, execute does not return the backstop error."""
    env = an_environment(held_by_label=None)
    git = FakeGit(base_exists=[True], branch_exists=[False])
    row = a_worktree_row()
    ctx = a_context(row, env=env, git=git)  # type: ignore[arg-type]

    result = GitWorktreeExecutor().execute(ctx)

    # The backstop reason must not appear — whatever path was taken.
    assert "branch held by" not in (result.reason or "")
    # Git was called (base was fetched or cloned).
    assert git.called("fetch_base") != [] or git.called("clone_base") != []
