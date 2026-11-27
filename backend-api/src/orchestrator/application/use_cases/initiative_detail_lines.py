"""The lines, facts and neighbours of one step or workflow of the initiative detail (story 6,
epic 7): what `initiative_detail_steps` composes a `DetailStep` and a `DetailWorkflow` with."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from orchestrator.application.rules.initiative_lines import (
    StripFact,
    TrackFact,
    step_token,
    strip_line,
    workflow_line,
)
from orchestrator.application.rules.initiative_status import StatusReading
from orchestrator.application.use_cases.initiative_facts import (
    current_conversation_row,
    ended_turns,
)
from orchestrator.application.use_cases.initiative_step_parts import (
    agent_of,
    forced,
    harness_model,
    park_of,
)
from orchestrator.application.use_cases.initiative_view_types import (
    InitiativeRow,
    InitiativeStepStatus,
    Loaded,
    StepFile,
    StepToken,
    WorkflowFile,
)
from orchestrator.application.use_cases.run_views_board import board_current_step_label
from orchestrator.application.use_cases.run_views_summary import progress
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import FrozenWorkflow
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git


def is_current(run: Run, row: StepRun, loaded: Loaded) -> bool:
    current = current_conversation_row(run, loaded.rows[run.id])
    return current is not None and current.id == row.id


def latest_run(runs: list[Run]) -> Run | None:
    return max(runs, key=lambda run: run.created_at, default=None)


@dataclass(frozen=True)
class StepContext:
    """What every step of the detail is composed with, read once by `initiative_detail`."""

    loaded: Loaded
    git: Git
    folder: str | None
    row: InitiativeRow
    reading: StatusReading
    prior: datetime | None
    history_files: Callable[[UUID], list[WorkflowFile]] | None


@dataclass(frozen=True)
class MergeFact:
    conflicts: int
    reason: str | None


@dataclass(frozen=True)
class At:
    """Where a step sits: its workflow, its place in it, and its neighbours."""

    index: int
    number: int
    k: int
    previous: str | None
    previous_is_gate: bool
    follows_current: bool


def auto_files_of(
    ctx: StepContext, entry: FrozenWorkflow, latest: Run | None
) -> list[WorkflowFile]:
    if entry.type != "auto" or latest is None or ctx.history_files is None:
        return []
    return ctx.history_files(latest.id)


def at_of(  # noqa: PLR0913, PLR0917 — one fact per argument
    ctx: StepContext,
    entry: FrozenWorkflow,
    index: int,
    number: int,
    listed: list[tuple[str, str]],
    k: int,
) -> At:
    previous = listed[k - 2][0] if k > 1 else None
    declared_gate = next(
        (d for d in entry.steps if d.id == previous and d.kind == "automatic"), None
    )
    latest = latest_run(ctx.loaded.runs)
    here = latest is not None and latest.initiative_position == index
    current = ctx.loaded.facts[latest.id].step if here and latest is not None else None
    follows = current is not None and previous == current
    return At(index, number, k, previous, declared_gate is not None, follows)


def track_line(  # noqa: PLR0913, PLR0917 — one fact per argument
    ctx: StepContext,
    entry: FrozenWorkflow,
    number: int,
    index: int,
    listed: list[tuple[str, str]],
    names: list[str],
) -> str:
    loaded = ctx.loaded
    sequence = loaded.initiative.sequence
    indices = {index} | {
        i
        for i in range(index + 1, len(sequence.workflows))
        if all(e.shown_as == "step" for e in sequence.workflows[index + 1 : i + 1])
    }
    own = [run for run in loaded.runs if run.initiative_position in indices]
    run = max(own, key=lambda r: r.created_at, default=None)
    ids = [step_id for step_id, _ in listed]
    k = ids.index(ctx.reading.step) + 1 if ctx.reading.step in ids else 1
    return workflow_line(
        TrackFact(
            type=entry.type,
            number=number,
            current=ctx.row.position,
            initiative_status=ctx.reading.status,
            attention=None if run is None else loaded.facts[run.id].attention,
            step=ctx.reading.step,
            k=k,
            j=len(listed),
            run=run,
            run_label="" if run is None else board_current_step_label(run, loaded.rows[run.id]),
            run_progress=None
            if run is None or entry.type != "auto"
            else progress(run, loaded.rows[run.id]),
            pr_merged_at=loaded.initiative.pr_merged_at,
            previous=names[number - 2] if number > 1 else None,
        )
    )


def facts_of(
    ctx: StepContext, run: Run | None, row: StepRun | None, decl: StepDecl | None
) -> dict[str, Any]:
    """The fields every step carries, read off its holder Run and row."""
    harness, model = harness_model(
        run, row, [] if run is None else ctx.loaded.records.get(run.id, [])
    )
    parked = park_of(run, row)
    return {
        "agent": None if decl is None else agent_of(decl),
        "harness": harness,
        "model": model,
        "run_id": None if run is None else run.id,
        "park_seq": parked.park_seq,
        "park_kind": parked.park_kind,
        "park_reason": parked.park_reason,
    }


def strip_of(  # noqa: PLR0913 — one fact per argument
    ctx: StepContext,
    at: At,
    *,
    status: InitiativeStepStatus,
    kind: str,
    run: Run | None,
    row: StepRun | None,
    turns: list[Attempt],
    files: list[StepFile],
    merge: MergeFact | None = None,
) -> str:
    loaded = ctx.loaded
    ended = [t.ended_at for t in turns if t.ended_at is not None]
    holder_reason = None if row is None else row.reason
    reason = holder_reason if merge is None else merge.reason
    return strip_line(
        StripFact(
            status=status,
            kind=kind,
            is_merge=merge is not None,
            forced=forced(row),
            reason=reason,
            ended_at=ended[-1] if ended else None if run is None else run.updated_at,
            file_names=tuple(PurePosixPath(f.path).name for f in files),
            is_current=row is not None and run is not None and is_current(run, row, loaded),
            attention=None if run is None else loaded.facts[run.id].attention,
            round=1 if run is None else run.initiative_round or 1,
            turns=len(ended_turns(turns)),
            conflicts=0 if merge is None else merge.conflicts,
            position_in_workflow=at.k - 1,
            previous_id=at.previous,
            previous_is_gate=at.previous_is_gate,
            follows_current=at.follows_current,
        )
    )


def token_of(ctx: StepContext, status: InitiativeStepStatus, row: StepRun | None) -> StepToken:
    cancelled = ctx.reading.status == "cancelled"
    return step_token(status, forced=forced(row), cancelled=cancelled)
