"""In-memory `AnalysisTools` — the one fake for that port (AD-18). Reuse it; do not write another.

A scripted `ToolRun` per tool, and optionally the text a tool writes to its `--report-path`
(made relative to `root` and written through the given workspace), so a test can feed a
recorded report to the code that reads it back. Every call is recorded.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from orchestrator.domain.ports.analysis_tools import ToolRun
from tests.unit.fakes.workspace import FakeWorkspace

UNSCRIPTED = ToolRun(exit=0, stdout="", stderr="", version="unknown")
REPORT_PATH = "--report-path"


class FakeAnalysisTools:
    def __init__(
        self,
        runs: Mapping[str, ToolRun] | None = None,
        writes: Mapping[str, str] | None = None,
        workspace: FakeWorkspace | None = None,
        root: Path = Path("/work/analysis"),
    ) -> None:
        self._runs = dict(runs or {})
        self._writes = dict(writes or {})
        self._workspace = workspace
        self._root = root
        self.calls: list[dict[str, Any]] = []

    def run(self, tool: str, args: Sequence[str], cwd: Path, timeout: float) -> ToolRun:
        self.calls.append({"tool": tool, "args": tuple(args), "cwd": cwd, "timeout": timeout})
        if tool in self._writes and self._workspace is not None and REPORT_PATH in args:
            report = Path(args[list(args).index(REPORT_PATH) + 1])
            self._workspace.write(str(report.relative_to(self._root)), self._writes[tool])
        return self._runs.get(tool, UNSCRIPTED)
