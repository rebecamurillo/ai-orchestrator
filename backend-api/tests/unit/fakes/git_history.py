"""In-memory fake for the `GitHistory` port (AD-18). Do not write another."""

from __future__ import annotations

from pathlib import Path

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat


class FakeGitHistory:
    """Answers from the dicts it is given; an unknown key answers `()` / `None`."""

    def __init__(
        self,
        stats: dict[tuple[str, str, str], tuple[FileStat, ...]] | None = None,
        subjects: dict[tuple[str, str], str] | None = None,
        error: GitError | None = None,
        diffs: dict[tuple[str, str, str, str], str] | None = None,
    ) -> None:
        self.stats = stats or {}
        self.subjects = subjects or {}
        self.error = error
        self.diffs = diffs or {}
        self.calls: list[tuple[str, ...]] = []

    def diff_stat(self, repo: Path, from_sha: str, to_sha: str) -> tuple[FileStat, ...]:
        self.calls.append(("diff_stat", str(repo), from_sha, to_sha))
        if self.error is not None:
            raise self.error
        return self.stats.get((str(repo), from_sha, to_sha), ())

    def commit_subject(self, repo: Path, sha: str) -> str | None:
        self.calls.append(("commit_subject", str(repo), sha))
        if self.error is not None:
            raise self.error
        return self.subjects.get((str(repo), sha))

    def diff_path(self, repo: Path, from_sha: str, to_sha: str, path: str) -> str:
        self.calls.append(("diff_path", str(repo), from_sha, to_sha, path))
        if self.error is not None:
            raise self.error
        return self.diffs.get((str(repo), from_sha, to_sha, path), "")
