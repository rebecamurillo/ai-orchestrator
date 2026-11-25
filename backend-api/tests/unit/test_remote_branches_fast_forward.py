"""`fast_forward_remote_branch` (epic 8 story 3, AC9): one plain push, never forced."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.git import GitError
from orchestrator.infrastructure.git.remote_branches import RemoteBranchesMixin

SHA = "a" * 40


class Runner(RemoteBranchesMixin):
    def __init__(self, error: GitError | None = None) -> None:
        self.commands: list[tuple[str, ...]] = []
        self.error = error

    def _run(self, *arguments: str) -> str:
        self.commands.append(arguments)
        if self.error is not None:
            raise self.error
        return ""


def test_the_branch_moves_with_one_plain_push() -> None:
    runner = Runner()

    runner.fast_forward_remote_branch(Path("/work/base"), "feat/snake", SHA)

    assert runner.commands == [
        ("-C", "/work/base", "push", "origin", "--", f"{SHA}:refs/heads/feat/snake")
    ]
    [command] = runner.commands
    assert not any(part.startswith("--force") or part == "-f" for part in command)


def test_a_refused_push_is_a_git_error() -> None:
    error = GitError(command="push", exit_code=1, output="non-fast-forward")

    with pytest.raises(GitError):
        Runner(error).fast_forward_remote_branch(Path("/work/base"), "feat/snake", SHA)
