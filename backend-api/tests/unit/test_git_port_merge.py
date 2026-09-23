"""`Git.merge`: the port contract the `git.merge` kind is written against (AD-14).

The method the spine's 2026-09-23 amendment adds to the port — "merge a ref into the
current worktree's branch, aborting any merge in progress first". Nothing here runs `git`:
what is asserted is the shape a use case is entitled to assume, and that the one shared fake
(AD-18) answers in it. The real commands are `tests/unit/test_subprocess_git_merge.py`.

**The contract, stated once.** `merge(worktree, branch)` answers

- the **merge commit's sha** when it merged something — `--no-ff`, so there is always a new
  commit and the sha is always new;
- **`None`** when `origin/{branch}` is already contained in the worktree's history, which is
  the port's own second convention ("not there is `None`") applied to "nothing to merge":
  `sync` already answers `None` for its own no-op, and the `git.merge` executor turns this
  one into the spine's `done · already merged`;
- and raises **`GitError`** on a conflict, carrying the conflicted-file listing in `output`.

A single `str` return could not tell the second case from the first without the caller
asking `head_sha` before and after and comparing — two calls to re-derive a fact the adapter
already had. The three answers are three facts, so the port states three.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.git import Git, GitError
from tests.unit.fakes.git import FakeGit

WORKTREE = Path("/work/acme/widgets/wt/develop")
FROM_BRANCH = "feat/epic-1"
MERGE_SHA = "beef0123456789abcdefbeef0123456789abcdef"
CONFLICT = "CONFLICT (content): Merge conflict in src/app.py\nsrc/app.py"


def test_merge_is_part_of_the_port_the_fake_satisfies() -> None:
    git: Git = FakeGit()

    assert isinstance(git, Git)
    assert hasattr(git, "merge")


def test_a_merge_answers_the_commit_it_made() -> None:
    git = FakeGit(merge=[MERGE_SHA])

    assert git.merge(WORKTREE, FROM_BRANCH) == MERGE_SHA


def test_a_ref_already_contained_answers_none_rather_than_a_sha() -> None:
    """The port's second convention: "nothing to do" is an ordinary answer, not an error."""
    git = FakeGit(merge=[None])

    assert git.merge(WORKTREE, FROM_BRANCH) is None


def test_a_conflict_is_a_git_error_carrying_the_listing() -> None:
    error = GitError(command="git merge", exit_code=1, output=CONFLICT)
    git = FakeGit(merge=[error])

    with pytest.raises(GitError) as raised:
        git.merge(WORKTREE, FROM_BRANCH)

    assert raised.value.output == CONFLICT


def test_every_merge_is_recorded_with_the_worktree_and_the_branch() -> None:
    git = FakeGit(merge=[MERGE_SHA])

    git.merge(WORKTREE, FROM_BRANCH)

    assert git.called("merge") == [(WORKTREE, FROM_BRANCH)]


def test_the_fake_merges_nothing_by_default() -> None:
    """The default answer is the harmless one: a fake nobody scripted has nothing to merge."""
    assert FakeGit().merge(WORKTREE, FROM_BRANCH) is None
