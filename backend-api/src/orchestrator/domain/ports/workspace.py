"""The `Workspace` port (AD-14): reading and writing the files of a Run's own worktree.

Rooted at `run.worktree_path` — every path a caller passes is relative to that root, never
absolute, and never allowed to walk out of it with a `..` segment. That is the whole reason
this port exists rather than a caller opening files itself: `application/` may not import
`shutil` or the filesystem (AD-2), and a Workspace built once per adapter would let a bug in
one Run's path reach a file of another's. `WorkspaceError` is the one refusal, whether the
cause is a path outside the root or a root that is not there yet — a Run's first row is
always `plan.check`, which runs before `git.worktree` has made a worktree to root one at.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class WorkspaceError(Exception):
    """A path this Workspace refuses: outside its root, or asked before the root exists."""


@dataclass(frozen=True)
class TreeEntry:
    """One file or directory `tree` found, named relative to the Workspace's own root."""

    path: str
    is_dir: bool


@runtime_checkable
class Workspace(Protocol):
    """Reads and writes rooted at one worktree; every path is relative and normalised."""

    def read(self, path: str) -> str | None:
        """The file's text, or `None` when nothing is there."""
        ...

    def write(self, path: str, text: str) -> None:
        """Write `text` to `path`, creating whatever directories it needs."""
        ...

    def exists(self, path: str) -> bool:
        """Whether `path` names a file or a directory under the root."""
        ...

    def glob(self, pattern: str) -> tuple[str, ...]:
        """Every path under the root matching `pattern`, in the filesystem's own order."""
        ...

    def move(self, src: str, dst: str) -> None:
        """Rename `src` to `dst`, both relative to the root."""
        ...

    def tree(self, prefix: str = "") -> tuple[TreeEntry, ...]:
        """Every file and directory under `prefix`, relative to the root."""
        ...

    def remove(self, path: str) -> None:
        """Remove the file or directory at `path`, recursively; already gone is not a
        failure (AD-14) — `worktree_gc` (SPEC CAP-11) calls this on a Run it may have swept
        before, and a second sweep must land as cleanly as the first."""
        ...
