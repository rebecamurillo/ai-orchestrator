"""In-memory `Git` that also holds remote branches — the fake for `RemoteBranches` (AD-18)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.git import FakeGit


class FakeRemoteGit(FakeGit):
    """`FakeGit` plus `create_remote_branch` and `delete_remote_branch`, over a set of branches
    the "origin" holds.

    A scripted answer that is an exception is raised instead of acting, as in `FakeGit`. A
    create adds the branch and, when `refs` is mapped, records its sha so `ls_remote` sees it;
    unscripted, a create of a held branch raises `GitError`.
    """

    def __init__(
        self,
        *,
        remote_branches: Iterable[str] = (),
        delete_remote_branch: list[Any] | None = None,
        create_remote_branch: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.remote_branches: set[str] = set(remote_branches)
        self._delete_script: list[Any] = delete_remote_branch or []
        self._deletes = 0
        self._create_script: list[Any] = create_remote_branch or []
        self._creates = 0

    def create_remote_branch(self, worktree: Path, branch: str, sha: str) -> None:
        self.calls.append(("create_remote_branch", (worktree, branch, sha)))
        if self._create_script:
            answer = self._create_script[min(self._creates, len(self._create_script) - 1)]
            self._creates += 1
            if isinstance(answer, BaseException):
                raise answer
        elif branch in self.remote_branches:
            raise GitError(command="push", exit_code=1, output=f"{branch} already exists")
        self.remote_branches.add(branch)
        if self.refs is not None:
            self.refs[branch] = sha

    def delete_remote_branch(self, worktree: Path, branch: str) -> bool:
        self.calls.append(("delete_remote_branch", (worktree, branch)))
        if self._delete_script:
            answer = self._delete_script[min(self._deletes, len(self._delete_script) - 1)]
            self._deletes += 1
            if isinstance(answer, BaseException):
                raise answer
        held = branch in self.remote_branches
        self.remote_branches.discard(branch)
        return held
