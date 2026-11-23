"""In-memory `Git` that also holds remote branches — the fake for `RemoteBranches` (AD-18)."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from tests.unit.fakes.git import FakeGit


class FakeRemoteGit(FakeGit):
    """`FakeGit` plus `delete_remote_branch`, over a set of branches the "origin" holds.

    A scripted answer that is an exception is raised instead of deleting, as in `FakeGit`.
    """

    def __init__(
        self,
        *,
        remote_branches: Iterable[str] = (),
        delete_remote_branch: list[Any] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.remote_branches: set[str] = set(remote_branches)
        self._delete_script: list[Any] = delete_remote_branch or []
        self._deletes = 0

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
