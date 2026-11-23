"""The `GitHistory` adapter: read-only `git diff --numstat` and `git log` for the step drawer.

The environment is built, not inherited, and carries no askpass or token variable (AD-5,
hard rule 5): `PATH`, an empty private `HOME`, `GIT_CONFIG_NOSYSTEM`, `GIT_TERMINAL_PROMPT`.
Shas go between `--end-of-options` and `--`, as argv entries, never into a shell.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat
from orchestrator.infrastructure.git.subprocess_git import (
    FALLBACK_PATH,
    NUL,
    TIMEOUT_EXIT_CODE,
    TIMEOUT_SECONDS,
)

_COUNT_PARTS = 3
_BINARY = "-"


def _count(text: str) -> int | None:
    return None if text == _BINARY else int(text)


def parse_numstat(output: str) -> tuple[FileStat, ...]:
    """Parse `--numstat -z`: `added\\tremoved\\tpath\\0`, a rename as `…\\t\\0old\\0new\\0`."""
    fields = output.split(NUL)
    stats: list[FileStat] = []
    index = 0
    while index < len(fields) and fields[index]:
        added, removed, path = fields[index].split("\t", _COUNT_PARTS - 1)
        index += 1
        if not path:
            path = fields[index + 1]
            index += 2
        stats.append(FileStat(path=path, added=_count(added), removed=_count(removed)))
    return tuple(stats)


class SubprocessGitHistory:
    def __init__(self, timeout: int = TIMEOUT_SECONDS) -> None:
        self._timeout = timeout
        self._home = tempfile.TemporaryDirectory(prefix="orchestrator-git-history-")

    def _run(self, repo: Path, *arguments: str) -> str:
        command = ["git", "-c", "credential.helper=", "-C", str(repo), *arguments]
        environment = {
            "PATH": os.environ.get("PATH") or FALLBACK_PATH,
            "HOME": self._home.name,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        try:
            completed = subprocess.run(  # fixed argv, no shell
                command,
                env=environment,
                capture_output=True,
                text=True,
                # a diff carries file contents, which need not be UTF-8
                errors="replace",
                timeout=self._timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise GitError(
                command=" ".join(command),
                exit_code=TIMEOUT_EXIT_CODE,
                output=f"timeout after {self._timeout} s",
            ) from error
        if completed.returncode != 0:
            raise GitError(
                command=" ".join(command),
                exit_code=completed.returncode,
                output=(completed.stdout + completed.stderr).strip() or "no output",
            )
        return completed.stdout

    def diff_stat(self, repo: Path, from_sha: str, to_sha: str) -> tuple[FileStat, ...]:
        output = self._run(
            repo,
            "-c",
            "core.quotePath=false",
            "diff",
            "--numstat",
            "-z",
            "--end-of-options",
            from_sha,
            to_sha,
            "--",
        )
        return parse_numstat(output)

    def commit_subject(self, repo: Path, sha: str) -> str | None:
        subject = self._run(repo, "log", "-1", "--format=%s", "--end-of-options", sha, "--").strip()
        return subject or None

    def diff_path(self, repo: Path, from_sha: str, to_sha: str, path: str) -> str:
        return self._run(
            repo,
            # `path` is a name git listed, which may hold `*` or `:(` — never a pattern
            "--literal-pathspecs",
            "-c",
            "core.quotePath=false",
            "diff",
            "--end-of-options",
            from_sha,
            to_sha,
            "--",
            path,
        )
