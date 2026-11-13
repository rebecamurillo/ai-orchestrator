"""The `metrics.analyse` kind: the code analysis of every repository the Run worked on.

The row never stops the Run: whatever goes wrong is a reason on a `done` row and the full
output on its log. Part C reads the pending analyses this row stores (SPEC CAP-4, T14).
"""

from __future__ import annotations

import traceback
from collections.abc import Sequence
from pathlib import Path

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.registry import register
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.values import StepResult

KIND = "metrics.analyse"

FAILED = "analysis failed: {line}"
ANALYSED = "{count} repositories analysed"
NO_PORT = "StepPorts.analysis is not set: the metrics.analyse kind needs it"


def _first_line(text: str) -> str:
    lines = text.splitlines()
    return lines[0] if lines else ""


def _ended(ctx: StepContext, line: str, text: str) -> StepResult:
    return StepResult(
        status="done",
        gate=ctx.row.gate,
        reason=FAILED.format(line=line),
        log_path=_write_log(ctx, text),
    )


def _write_log(ctx: StepContext, text: str) -> str | None:
    if ctx.ports.workspace is None:
        return None
    path: Path = log_path(ctx)
    ctx.ports.workspace(str(path.parent)).write(path.name, text)
    return str(path)


def _failed_analysis(found: Sequence[Analysis]) -> Analysis | None:
    failed = [analysis for analysis in found if analysis.status == "failed"]
    return min(failed, key=lambda a: a.repository_path, default=None)


class MetricsAnalyseExecutor:
    """Run the analysis, store it pending, and end `done` whatever happens."""

    def execute(self, ctx: StepContext) -> StepResult:
        if ctx.ports.analysis is None:
            return _ended(ctx, NO_PORT, NO_PORT)
        try:
            found = ctx.ports.analysis(ctx.attempt.run_id)
        except Exception as error:
            text = "".join(traceback.format_exception(error))
            return _ended(ctx, _first_line(str(error)), text)
        failed = _failed_analysis(found)
        if failed is not None:
            lines = "\n".join(f"{a.repository_path}: {a.status} {a.output}" for a in found)
            line = f"{failed.repository_path}: {_first_line(failed.output)}"
            return _ended(ctx, line, lines)
        return StepResult(
            status="done", gate=ctx.row.gate, reason=ANALYSED.format(count=len(found))
        )


register(KIND, MetricsAnalyseExecutor())
