"""`RemoteBranches` for the subprocess adapter: a mixin over `SubprocessGit`'s `_run`.

Every command inherits the adapter's credential path and output redaction (AD-5).
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from orchestrator.domain.ports.git import GitError
from orchestrator.infrastructure.git.worktrees import END_OF_OPTIONS, ORIGIN

#: What git answers when the remote holds no such branch.
REF_ABSENT = "remote ref does not exist"


class _Runner(Protocol):
    def _run(self, *arguments: str) -> str: ...


class RemoteBranchesMixin:
    def delete_remote_branch(self: _Runner, worktree: Path, branch: str) -> bool:
        """Never forced, never retried; only the absent-ref answer is not an error."""
        try:
            self._run("-C", str(worktree), "push", ORIGIN, "--delete", END_OF_OPTIONS, branch)
        except GitError as error:
            if REF_ABSENT in error.output:
                return False
            raise
        return True
