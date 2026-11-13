"""The `AnalysisTools` port: one external analysis tool, run to completion in a folder.

The process gets no environment beyond the runner's own five names (AD-5): a tool never
sees `GITHUB_TOKEN` or a gateway key. `stdout` holds the combined output (the runner writes
one log); `stderr` is empty for the subprocess adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ToolRun:
    """`exit` is `None` when the deadline killed the tool."""

    exit: int | None
    stdout: str
    stderr: str
    version: str
    timed_out: bool = False


@runtime_checkable
class AnalysisTools(Protocol):
    def run(self, tool: str, args: Sequence[str], cwd: Path, timeout: float) -> ToolRun:
        """Run `tool` with `args` in `cwd`; `timeout` is in minutes, as for `ProcessRunner`."""
        ...
