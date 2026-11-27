"""The two lines an initiative row shows under its name (EXPERIENCE I1).

Pure: the step line and the progress line are composed from facts the caller already read.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import InitiativeStatusValue, StatusReading
from orchestrator.application.use_cases.initiative_view_types import (
    FilesState,
    InitiativeStepStatus,
    StepToken,
)
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


@dataclass(frozen=True)
class StripFact:
    """What one step of the initiative page's steps strip is composed from (EXPERIENCE I3)."""

    status: InitiativeStepStatus
    kind: str
    is_merge: bool
    forced: bool
    reason: str | None
    ended_at: datetime | None
    file_names: tuple[str, ...]
    is_current: bool
    attention: Attention | None
    round: int
    turns: int
    conflicts: int
    position_in_workflow: int
    previous_id: str | None
    previous_is_gate: bool
    follows_current: bool


@dataclass(frozen=True)
class TrackFact:
    """What one workflow's line of fact is composed from (EXPERIENCE I3 "Workflow track")."""

    type: str
    number: int
    current: int
    initiative_status: InitiativeStatusValue
    attention: Attention | None
    step: str
    k: int
    j: int
    run: Run | None
    run_label: str
    run_progress: Progress | None
    pr_merged_at: datetime | None
    previous: str | None


def step_token(status: InitiativeStepStatus, *, forced: bool, cancelled: bool) -> StepToken:
    if cancelled and status in ("planned", "running", "waiting for her"):
        return "CAN"
    if status == "skipped":
        return "SKP" if forced else "DON"
    return _TOKENS[status]


def files_state(status: InitiativeStepStatus, *, forced: bool) -> FilesState:
    if status == "skipped":
        return "skipped, forced" if forced else "done"
    return _FILES[status]


def strip_line(fact: StripFact) -> str:
    """The first rule that matches; the order is the rule (the automatic step's own sentence
    sits before `waiting for her` and `failed`)."""
    for rule in _STRIP_RULES:
        found = rule(fact)
        if found is not None:
            return found
    return _strip_planned(fact)


def _strip_done(fact: StripFact) -> str | None:
    if fact.status != "done":
        return None
    word = "merged" if fact.is_merge else "closed"
    if fact.ended_at is None:
        return word
    line = f"{word} {fact.ended_at:%Y-%m-%d}"
    if fact.is_merge or not fact.file_names:
        return line
    return f"{line} · {', '.join(fact.file_names)}"


def _strip_skipped(fact: StripFact) -> str | None:
    if fact.status != "skipped":
        return None
    if not fact.forced:
        return fact.reason or "skipped"
    if fact.ended_at is None:
        return "skipped, forced"
    return f"skipped, forced · {fact.ended_at:%H:%M}"


def _strip_conflict(fact: StripFact) -> str | None:
    if fact.conflicts <= 0:
        return None
    noun = "file" if fact.conflicts == 1 else "files"
    return f"conflict · {fact.conflicts} {noun} · your turn"


def _strip_own_sentence(fact: StripFact) -> str | None:
    return fact.reason if fact.kind == "automatic" and fact.reason else None


def _strip_waiting(fact: StripFact) -> str | None:
    if fact.status != "waiting for her":
        return None
    if fact.reason:
        return f"needs you · {fact.reason}"
    return f"round {fact.round} · your turn" if fact.round > 1 else "needs you"


def _strip_failed(fact: StripFact) -> str | None:
    if fact.status != "failed":
        return None
    return f"failed · {fact.reason}" if fact.reason else "failed"


def _strip_running(fact: StripFact) -> str | None:
    if fact.status != "running":
        return None
    if fact.kind == "conversation" and fact.is_current:
        if fact.attention == "your_turn":
            if fact.round > 1:
                return f"round {fact.round} · your turn"
            return f"your turn · {fact.turns} turns"
        if fact.attention in _ANSWERING:
            return "agent answering"
    return "running"


def _strip_planned(fact: StripFact) -> str:
    """What is left once every other status has answered."""
    if fact.follows_current and fact.kind == "conversation":
        return "next"
    if fact.previous_is_gate:
        return "starts after the gate passes"
    return f"starts after {fact.previous_id}" if fact.previous_id else ""


_STRIP_RULES: tuple[Callable[[StripFact], str | None], ...] = (
    _strip_done,
    _strip_skipped,
    _strip_conflict,
    _strip_own_sentence,
    _strip_waiting,
    _strip_failed,
    _strip_running,
)

_TOKENS: dict[str, StepToken] = {
    "running": "RUN",
    "waiting for her": "BLK",
    "done": "DON",
    "failed": "ERR",
    "planned": "QUE",
}
_FILES: dict[str, FilesState] = {
    "done": "done",
    "running": "open",
    "waiting for her": "open",
    "planned": "to come",
    "failed": "failed",
}


def workflow_line(fact: TrackFact) -> str:
    """The workflow track's line of fact: the first rule that matches."""
    run = fact.run
    if run is None:
        return f"starts by itself when {fact.previous} is done" if fact.previous else ""
    if fact.initiative_status == "cancelled" and fact.number == fact.current:
        return "cancelled"
    if fact.type == "interactive":
        return _interactive_line(fact, run)
    return _auto_line(fact, run)


def _interactive_line(fact: TrackFact, run: Run) -> str:
    if fact.number == fact.current and fact.initiative_status != "done":
        if fact.attention == "your_turn":
            state = "your turn"
        elif fact.attention in _ANSWERING:
            state = "agent answering"
        elif fact.initiative_status == "waiting for her":
            state = "needs you"
        elif fact.initiative_status == "failed":
            state = "failed"
        else:
            state = "running"
        return f"step {fact.k} of {fact.j} · {fact.step} · {state}"
    when = run.updated_at or run.created_at
    return f"completed {when:%Y-%m-%d} · {fact.j}/{fact.j} steps"


def _auto_line(fact: TrackFact, run: Run) -> str:
    if run.status == "done":
        if fact.pr_merged_at is not None:
            return f"completed {fact.pr_merged_at:%Y-%m-%d}"
        if run.compare_urls:
            return f"Run done · pull request {', '.join(run.compare_urls)} not merged"
        return "Run done"
    counts = progress_line("auto", k=1, j=1, run=run, run_progress=fact.run_progress)
    line = " · ".join(part for part in (fact.run_label, counts) if part)
    return f"{line} / ${run.budget_usd:.2f}" if run.budget_usd is not None else line
