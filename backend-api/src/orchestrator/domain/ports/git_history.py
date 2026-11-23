"""The `GitHistory` port: what a range of commits changed, for the step drawer (AD-40).

Split from `Git` for its 400-line module cap. Both methods raise `GitError` on failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class FileStat:
    """One path of a `--numstat`; `None` counts mean a binary file."""

    path: str
    added: int | None
    removed: int | None


@runtime_checkable
class GitHistory(Protocol):
    """Reads commit history in an existing repository; never writes."""

    def diff_stat(self, repo: Path, from_sha: str, to_sha: str) -> tuple[FileStat, ...]:
        """Per-file line counts between two commits; raises `GitError`."""
        ...

    def commit_subject(self, repo: Path, sha: str) -> str | None:
        """The commit's subject line, `None` when empty; raises `GitError`."""
        ...
