"""The per-step facts of the initiative detail that are read off one Run's rows (story 6, epic 7).

Pure over values already read; the one port touched is `Git`, for the files of a turn range.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from orchestrator.application.rules import merge_conflicts, session
from orchestrator.application.rules.signals import row_at
from orchestrator.application.use_cases.initiative_view_types import StepFile, TurnStatus
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.statuses import ParkKind

FORCED_REASON = "skipped, forced"
MERGE_KIND = "git.merge"


def step_number(workflow_number: int, k: int) -> str:
    return f"{workflow_number}.{k}"


def agent_of(decl: StepDecl) -> str | None:
    """The persona file's stem of a `conversation` step, `None` for an automatic one."""
    if decl.kind != "conversation" or not decl.persona:
        return None
    return PurePosixPath(decl.persona).stem


def harness_model(
    run: Run | None, row: StepRun | None, records: Sequence[GateRecord]
) -> tuple[str | None, str | None]:
    """The step session's `session_start` payload, else the Run's inputs."""
    if run is None:
        return None, None
    started = [
        r
        for r in records
        if r.event == session.SESSION_START
        and row is not None
        and r.path == row.path
        and r.payload.get(session.SCOPE_KEY) == session.STEP_SCOPE
    ]
    if started:
        payload = started[-1].payload
        return _text(payload.get(session.HARNESS_KEY)), _text(payload.get(session.MODEL_KEY))
    return _text(run.inputs.get(session.HARNESS_KEY)), _text(run.inputs.get(session.MODEL_KEY))


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


class Parked(NamedTuple):
    park_seq: int | None
    park_kind: ParkKind | None
    park_reason: str | None


def park_of(run: Run | None, row: StepRun | None) -> Parked:
    """The stop the Run is parked in, when it is parked at `row` (any row when `row` is `None`)."""
    if run is None or run.status != "needs_you":
        return Parked(None, None, None)
    if row is not None and run.park_path != row.path:
        return Parked(None, None, None)
    return Parked(run.park_seq, run.park_kind, run.park_reason)


def conflicts_of(
    run: Run | None, rows: Sequence[StepRun], attempts: Sequence[Attempt]
) -> list[str]:
    """The unmerged paths of a `merge_conflict` stop, from the parked `git.merge` row."""
    if run is None or run.park_kind != "merge_conflict":
        return []
    row = row_at(rows, run.park_path)
    if row is None or row.kind != MERGE_KIND:
        return []
    latest = max((a for a in attempts if a.step_run_id == row.id), key=lambda a: a.n, default=None)
    return [] if latest is None else merge_conflicts.conflict_files(latest.output_ref)


def turn_status(attempt: Attempt) -> TurnStatus:
    if attempt.status in ("queued", "planned"):
        return "queued"
    if attempt.status == "running":
        return "running"
    return "failed" if attempt.status in ("error", "blocked") else "done"


def forced(row: StepRun | None) -> bool:
    return (
        row is not None and row.status == "skipped" and (row.reason or "").startswith(FORCED_REASON)
    )


def timed_files(
    by_run: list[tuple[Run, list[Attempt]]],
    git: Git,
    folder: str | None,
    *,
    draft: bool,
    prior: datetime | None,
) -> list[StepFile]:
    """The step folder's changed paths, each with the latest Run whose turn range lists it."""
    found: dict[str, tuple[Run, datetime | None]] = {}
    for run, attempts in by_run:
        if folder is None or not run.worktree_path or run.worktrees_removed:
            continue
        first, last = attempts[0].start_sha, attempts[-1].end_sha
        if first is None or last is None:
            continue
        try:
            changes = git.diff_changes(Path(run.worktree_path), first, last)
        except GitError:
            continue
        for change in changes:
            if change.path.startswith(folder):
                found[change.path] = (run, attempts[-1].ended_at)
    return [
        StepFile(
            path=path,
            draft=draft,
            run_id=run.id,
            time=time,
            changed=prior is not None and time is not None and time > prior,
        )
        for path, (run, time) in found.items()
    ]
