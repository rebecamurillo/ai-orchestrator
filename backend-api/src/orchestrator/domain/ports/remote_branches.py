"""The port for deleting a branch on the remote.

`worktree` is any local clone — a Run's worktree or the project's base clone. Epic 7 story 3
extends this port with `create_remote_branch`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class RemoteBranches(Protocol):
    def delete_remote_branch(self, worktree: Path, branch: str) -> bool:
        """Delete `branch` on `origin`; `False` when the remote does not hold it."""
        ...
