"""`application/steps/git_commit.py`: the commit-guard (FR-10, FR-16, AD-17).

Four rules, each asserted where it can only be settled here: the staging *order*, which only
a call log shows; "nothing staged is `done`", which is what keeps a verify row that changed
nothing from failing a Run; the protected-path seam, over a fake that reports hits; and the
message being the row's own, never composed.

A `with {workdir}` row (H2, 2026-09-23, spine AD-9 amendment) is asserted separately, below:
the port is called with `workdir` instead of the staging sequence running, and `None` back
from it parks the same sentence `git.submodule` and `git.push` do.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from orchestrator.application.steps.context import NO_ENVIRONMENT, StepExecutor
from orchestrator.application.steps.git_commit import (
    KIND,
    NO_CHANGES,
    NOT_A_SUBMODULE,
    PROTECTED,
    GitCommitExecutor,
)
from orchestrator.application.steps.registry import executor_for
from orchestrator.domain.entities.step_run import StepRun
from tests.unit.fakes.git import DEFAULT_SHA, FakeGit
from tests.unit.step_fixtures import (
    WORKTREE,
    a_context,
    a_row,
    an_environment,
    without,
)

MESSAGE = "story 4-8: git step kinds (orchestrator)"
SPEC_FOLDER = "_bmad-output/planning-artifacts/mvp/epics/epic-04-runs"
DIRTY = "?? src/new.py\n M src/thing.py\n"
WORKDIR = "repos/member"
MEMBER_SHA = "beef0123456789abcdefbeef0123456789abcdef"


class Hits:
    """A `ProtectedPaths` that reports whatever it was built with — Epic 5's rule, faked."""

    def __init__(self, *hits: str) -> None:
        self.hits = hits
        self.calls: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def check(self, *, changed: Sequence[str], accepted: Sequence[str]) -> tuple[str, ...]:
        self.calls.append((tuple(changed), tuple(accepted)))
        return self.hits


def a_commit_row() -> StepRun:
    return a_row(kind=KIND, with_resolved={"message": MESSAGE}, path="stories[0].commit-guard")


def test_the_executor_satisfies_the_protocol_and_is_the_registered_one() -> None:
    assert isinstance(GitCommitExecutor(), StepExecutor)
    assert isinstance(executor_for(KIND), GitCommitExecutor)


def test_a_worktree_with_no_changes_is_done_and_commits_nothing() -> None:
    git = FakeGit(status=[""])

    result = GitCommitExecutor().execute(a_context(a_commit_row(), git=git))

    assert result.status == "done"
    assert result.reason == NO_CHANGES
    assert git.called("commit") == []


def test_the_spec_folder_is_staged_first_and_then_everything_else() -> None:
    git = FakeGit(status=[DIRTY])
    context = a_context(a_commit_row(), git=git, env=an_environment(spec_folder=SPEC_FOLDER))

    GitCommitExecutor().execute(context)

    assert [pathspec for _, pathspec in git.called("stage")] == [SPEC_FOLDER, None]


def test_a_run_with_no_spec_folder_stages_everything_once() -> None:
    git = FakeGit(status=[DIRTY])

    GitCommitExecutor().execute(a_context(a_commit_row(), git=git))

    assert [pathspec for _, pathspec in git.called("stage")] == [None]


def test_the_commit_carries_the_message_the_row_resolved_and_answers_its_sha() -> None:
    git = FakeGit(status=[DIRTY])

    result = GitCommitExecutor().execute(a_context(a_commit_row(), git=git))

    [(worktree, message)] = git.called("commit")
    assert str(worktree) == WORKTREE
    assert message == MESSAGE
    assert result.status == "done"
    assert result.output_ref == DEFAULT_SHA


def test_an_untracked_file_alone_is_a_change_worth_committing() -> None:
    git = FakeGit(status=["?? src/new.py\n"])

    assert GitCommitExecutor().execute(a_context(a_commit_row(), git=git)).status == "done"
    assert git.called("commit")


def test_with_no_rule_wired_nothing_is_protected_and_the_commit_happens() -> None:
    """Epic 4 wires none; `domain/ports/protected_paths.py` says why that is not a green check."""
    git = FakeGit(status=[DIRTY])

    result = GitCommitExecutor().execute(a_context(a_commit_row(), git=git))

    assert result.status == "done"
    assert git.called("commit")


def test_a_protected_path_parks_the_run_and_commits_nothing() -> None:
    git = FakeGit(status=[DIRTY])
    rule = Hits("tests/unit/test_thing.py")
    context = a_context(a_commit_row(), git=git, protected_paths=rule)

    result = GitCommitExecutor().execute(context)

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "protected_path"
    assert result.park.reason == PROTECTED.format(paths="tests/unit/test_thing.py")
    assert git.called("commit") == []


def test_the_rule_is_asked_about_the_staged_paths_and_the_accepted_ones() -> None:
    git = FakeGit(status=[DIRTY])
    rule = Hits()
    context = a_context(
        a_commit_row(),
        git=git,
        protected_paths=rule,
        env=an_environment(accepted_paths=("AGENTS.md",)),
    )

    GitCommitExecutor().execute(context)

    assert rule.calls == [(("src/new.py", "src/thing.py"), ("AGENTS.md",))]


def test_without_an_environment_the_executor_refuses() -> None:
    with pytest.raises(RuntimeError, match=NO_ENVIRONMENT):
        GitCommitExecutor().execute(without(a_context(a_commit_row()), run_env=None))


# ── `with {workdir}` (H2, spine AD-9 amendment, 2026-09-23) ─────────────────


def a_workdir_commit_row() -> StepRun:
    return a_row(
        kind=KIND,
        with_resolved={"message": MESSAGE, "workdir": WORKDIR},
        path="stories[0].epics[0].commit-guard",
    )


def test_a_workdir_row_commits_in_the_submodule_instead_of_staging_at_the_root() -> None:
    git = FakeGit(commit=[MEMBER_SHA])

    result = GitCommitExecutor().execute(a_context(a_workdir_commit_row(), git=git))

    assert result.status == "done"
    assert result.output_ref == MEMBER_SHA
    [(worktree, message, workdir)] = git.called("commit")
    assert (str(worktree), message, workdir) == (WORKTREE, MESSAGE, WORKDIR)
    assert git.called("stage") == []
    assert git.called("status") == []


def test_a_workdir_that_is_not_an_initialized_submodule_parks_the_spines_sentence() -> None:
    git = FakeGit(commit=[None])

    result = GitCommitExecutor().execute(a_context(a_workdir_commit_row(), git=git))

    assert result.status == "error"
    assert result.park is not None
    assert result.park.kind == "misconfigured"
    assert result.park.reason == f"workdir {WORKDIR} is not an initialized submodule"
    assert result.reason == NOT_A_SUBMODULE.format(path=WORKDIR)
    assert result.output_ref is None


def test_a_workdir_row_never_runs_the_protected_path_check() -> None:
    """Owed to H4 (module docstring): the dual-tree check needs the `agent` kind's own
    `workdir` machinery, which this story does not touch."""
    rule = Hits("tests/unit/test_thing.py")
    git = FakeGit(commit=[MEMBER_SHA])

    result = GitCommitExecutor().execute(
        a_context(a_workdir_commit_row(), git=git, protected_paths=rule)
    )

    assert result.status == "done"
    assert rule.calls == []
