"""The port for creating and deleting a branch on the remote.

`worktree` is any local clone — a Run's worktree or the project's base clone.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class RemoteBranches(Protocol):
    def create_remote_branch(self, worktree: Path, branch: str, sha: str) -> None:
        """Create `branch` on `origin` at `sha`; an existing branch raises `GitError`."""
        ...

    def fast_forward_remote_branch(self, worktree: Path, branch: str, sha: str) -> None:
        """Move `branch` on `origin` to `sha`, never forced; a rejected push raises `GitError`."""
        ...

    def delete_remote_branch(self, worktree: Path, branch: str) -> bool:
        """Delete `branch` on `origin`; `False` when the remote does not hold it."""
        ...
