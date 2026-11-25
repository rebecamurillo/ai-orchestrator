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
    def create_remote_branch(self: _Runner, worktree: Path, branch: str, sha: str) -> None:
        """Never forced, never retried."""
        ref = f"refs/heads/{branch}"
        held = self._run("-C", str(worktree), "ls-remote", "--heads", ORIGIN, END_OF_OPTIONS, ref)
        if held.strip():
            raise GitError(
                command=f"git push {ORIGIN} {ref}", exit_code=1, output=f"{branch} already exists"
            )
        # Git calls a push of the sha the remote already holds up to date, so the check above
        # names that case; the empty-expect lease closes the race after it, where a plain push
        # would fast-forward a branch created in between.
        self._run(
            "-C",
            str(worktree),
            "push",
            f"--force-with-lease={ref}:",
            ORIGIN,
            END_OF_OPTIONS,
            f"{sha}:{ref}",
        )

    def delete_remote_branch(self: _Runner, worktree: Path, branch: str) -> bool:
        """Never forced, never retried; only the absent-ref answer is not an error."""
        try:
            self._run("-C", str(worktree), "push", ORIGIN, "--delete", END_OF_OPTIONS, branch)
        except GitError as error:
            if REF_ABSENT in error.output:
                return False
            raise
        return True
