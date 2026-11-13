"""The analysis half of the `Git` port: reading what a Run pushed, from a scratch clone.

Split from `git.py` for the 400-line module cap; `Git` inherits it, so there is one port.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol


@dataclass(frozen=True)
class NumstatEntry:
    """One path of `git diff --numstat`; a binary file counts 0 added and 0 removed."""

    path: str
    added: int
    removed: int
    binary: bool


@dataclass(frozen=True)
class NameStatus:
    """One path of `git diff --name-status -M`; `old_path` is set for `R` and `C`."""

    status: Literal["A", "M", "D", "R", "C", "T"]
    path: str
    old_path: str | None


class AnalysisGit(Protocol):
    """Commands the metrics analysis runs in a scratch clone."""

    def fetch(self, remote_url: str, refs: tuple[str, ...], into: Path) -> None:
        """Initialise `into` (parents created) when it is not yet a repository, then fetch
        the refspecs from `remote_url` with no tags and no filter.

        Raises `GitError` on any failure, including a ref or SHA the remote does not hold.
        """
        ...

    def merge_base(self, dest: Path, a: str, b: str) -> str | None:
        """The best common ancestor of `a` and `b`; `None` when they share none."""
        ...

    def diff_numstat(self, dest: Path, base: str, head: str) -> tuple[NumstatEntry, ...]:
        """Added/removed line counts per path, `-M`; `()` for a ref the clone does not hold."""
        ...

    def diff_name_status(self, dest: Path, base: str, head: str) -> tuple[NameStatus, ...]:
        """How each path changed, with rename detection (`-M`); `()` for an unknown ref."""
        ...

    def diff_text(self, dest: Path, base: str, head: str, paths: tuple[str, ...]) -> str:
        """Unified diff with zero context; empty `paths` is the whole diff; `""` for an
        unknown ref."""
        ...

    def commits_between(self, dest: Path, base: str, head: str) -> tuple[str, ...]:
        """`rev-list base..head`, newest first; `()` for an unknown ref."""
        ...
