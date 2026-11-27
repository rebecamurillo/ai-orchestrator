"""What a deterministic kind writes into its log (AD-40 "Writing").

`GitRecorder` stands in for the `Git` port and notes each call and its answer in words, so a
failed row explains itself; `logged` hands it to a kind's body and stores the lines through the
`StepLog` port once the body returns. File content is never logged: `read_file` answers a line
count, because a list file can hold anything a Repository holds.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

from orchestrator.application.steps.context import StepContext
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.values import StepResult

#: The `Git` method whose answer is file content, logged as a count.
READ_FILE = "read_file"

#: Indentation of an answer line under its operation line.
INDENT = "  "


class GitRecorder:
    """Delegates every `Git` attribute and records each call in `lines`."""

    def __init__(self, git: Git) -> None:
        self._git = git
        self.lines: list[str] = []

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._git, name)
        if not callable(attribute):
            return attribute

        def recorded(*args: Any, **kwargs: Any) -> Any:
            operands = [*map(str, args), *map(str, kwargs.values())]
            self.lines.append("> " + " ".join([name, *operands]))
            try:
                answer = attribute(*args, **kwargs)
            except GitError as error:
                self.lines.append(f"{INDENT}error · exit {error.exit_code}")
                self.lines.extend(f"{INDENT}{line}" for line in error.output.splitlines())
                raise
            self.lines.extend(_answer_lines(name, answer))
            return answer

        return recorded


def _answer_lines(method: str, answer: object) -> list[str]:
    if method == READ_FILE and (answer is None or isinstance(answer, str)):
        return [
            f"{INDENT}absent" if answer is None else f"{INDENT}{len(answer.splitlines())} lines"
        ]
    if answer is None:
        return []
    if isinstance(answer, bool):
        return [f"{INDENT}{'yes' if answer else 'no'}"]
    if isinstance(answer, str):
        return [f"{INDENT}{line}" for line in answer.splitlines()]
    if isinstance(answer, tuple):
        return [f"{INDENT}{item}" for item in answer]
    return [f"{INDENT}{answer}"]


def write_step_log(ctx: StepContext, lines: Sequence[str]) -> str | None:
    """Store the log of this attempt; `None` when no `StepLog` is wired."""
    if ctx.ports.step_log is None:
        return None
    return ctx.ports.step_log.write(ctx.attempt.run_id, ctx.row.seq, ctx.attempt.n, lines)


def logged(ctx: StepContext, body: Callable[[StepContext, GitRecorder], StepResult]) -> StepResult:
    """Run `body` with every git call of the row going through one recorder.

    The recording context replaces `ctx.ports.git`, so calls made by helpers and by `records`
    are logged too. A raise inside `body` propagates and writes no log.
    """
    recorder = GitRecorder(ctx.ports.git)
    inner = replace(ctx, ports=replace(ctx.ports, git=cast(Git, recorder)))
    result = body(inner, recorder)
    return result.model_copy(update={"log_path": write_step_log(ctx, recorder.lines)})


def head_or_none(git: Git, worktree: Path) -> str | None:
    """`head_sha`, with a failure read as no head: the refs line must not change the outcome."""
    try:
        return git.head_sha(worktree)
    except GitError:
        return None


def refs_line(before: str | None, after: str | None, branch: str) -> str | None:
    """The `refs updated:` line when the head moved, else `None`."""
    if before is None or after is None or before == after:
        return None
    return f"refs updated: {branch} {before[:7]} → {after[:7]}"
