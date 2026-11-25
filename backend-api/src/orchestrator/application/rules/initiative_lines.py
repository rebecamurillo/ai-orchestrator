"""The two lines an initiative row shows under its name (EXPERIENCE I1).

Pure: the step line and the progress line are composed from facts the caller already read.
"""

from __future__ import annotations

from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import StatusReading
from orchestrator.application.use_cases.run_view_types import Progress
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run

_ANSWERING: tuple[Attention, ...] = ("answering", "queued")


def step_line(  # noqa: PLR0911, PLR0913 — one return per row of the table, one fact per argument
    initiative: Initiative,
    reading: StatusReading,
    attention: Attention | None,
    *,
    ended_turns: int,
    current_label: str,
    harness: str | None,
) -> str:
    """The first row of the table that matches."""
    if reading.status == "cancelled":
        error = initiative.branch_cleanup_error
        if error is None:
            return "spec branch deleted · slug free"
        return f"cancelled · branch cleanup failed: {error}"
    if reading.status == "done":
        merged = initiative.pr_merged_at
        stamp = f"{merged:%Y-%m-%d}" if merged is not None else ""
        return f"build done · pull request merged {stamp}"
    if attention == "your_turn":
        return f"your turn · conversation, {ended_turns} turns"
    if attention in _ANSWERING:
        return "agent answering"
    if reading.status == "waiting for her":
        return f"needs you · {reading.reason or reading.step}"
    if reading.status == "failed":
        return f"failed · {reading.reason}" if reading.reason else "failed"
    if reading.status == "running" and reading.reason:
        return reading.reason
    return " · ".join(part for part in (current_label or reading.step, harness) if part)


def progress_line(
    workflow_type: str,
    *,
    k: int,
    j: int,
    run: Run | None,
    run_progress: Progress | None,
) -> str:
    """`step {k} of {j}` for an interactive workflow, the Run's own counts for an auto one."""
    if workflow_type == "interactive":
        return f"step {k} of {j}"
    if run is None:
        return ""
    return f"{_counts(run, run_progress)} · ${run.spend_usd:.2f}"


def _counts(run: Run, progress: Progress | None) -> str:
    if progress is None:
        return run.template_name
    epics = (
        f"{progress.epics_done}/{progress.epics_total} epics · "
        if progress.epics_total is not None
        else ""
    )
    noun = "link" if progress.links == 1 else "links"
    return (
        f"{epics}{progress.stories_done}/{progress.stories_total} stories · {progress.links} {noun}"
    )
