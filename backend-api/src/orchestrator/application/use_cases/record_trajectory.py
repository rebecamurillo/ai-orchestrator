"""`record_trajectory` (SPEC CAP-9, AD-19, FR-32): one append-only row per Story that
reaches `done` — what ran, how many attempts, what the gates said, what it cost, and the
story file as committed.

Called from `apply_step_result` the instant a Story frame's own commit-guard row itself ends
`done` — the frame's last row, and the only point at which `end_sha` ("HEAD after the
commit-guard") is a fact rather than a guess. By construction the walk never reaches that row
until the frame's `build` row is `done` and its `verify` row is `done | skipped`
(`templates/story.yaml`'s own order — `verify`'s `on_fail` sends a failure back to `build`,
and the commit-guard is queued only once `verify` finishes), so the two checks below are a
safety belt over an unusual Template shape, not the gate. `skip_story` reaches the same row
the same way: `application/use_cases/signal_effects.py::_skip_frame` rewrites the
commit-guard's message and re-queues it rather than skipping it, so an Operator-skipped Story
still completes through this same trigger — no second wiring needed.

Idempotent on `(run_id, frame)` (AD-19): `TrajectoryRepository.add` does nothing on a second
call for the same pair, which is what makes a durable-step replay safe to call twice. Nothing
here updates or deletes — the repository port exposes `add` and `list_for_project` only.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from orchestrator.application.rules.frames import in_frame, rows_in_frame
from orchestrator.application.steps import AGENT_KIND, COMMIT_KIND, SHELL_KIND
from orchestrator.application.steps.git_commit import NO_CHANGES
from orchestrator.application.templates.agent_row import SPEC_FOLDER_KEY
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.entities.trajectory import (
    AttemptRecord,
    GateResults,
    HumanAction,
    ProtectedPathHit,
    ProtectedPathsResult,
    Trajectory,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.trajectories import TrajectoryRepository
from orchestrator.domain.statuses import PARK_KINDS, SIGNAL_KINDS

#: The one `StepStatus` value every "is this row finished, successfully" check below wants.
DONE = "done"
SKIPPED = "skipped"

#: A frame's own gate record is a "human action" when it is a stop (a park) or an Operator's
#: own signal — never the automatic bookkeeping AD-9 records without either (`redispatch`,
#: `retry_auto`) and never a Run's own lifecycle line (`start`/`done`/`failed`/`cancelled`).
HUMAN_EVENTS = frozenset({*PARK_KINDS, *SIGNAL_KINDS})

#: `application/steps/agent_tail.py::HITS_KEY` restated: the key a `protected_path` gate
#: record's payload carries its hit list under. Not imported — that module is the tail's,
#: this one only reads the string the two already agree on.
HITS_KEY = "hits"

#: The park kind AD-17's own protected-path check records its hits under.
PROTECTED_PATH = "protected_path"

_EPIC_INDEX = re.compile(r"epics\[(\d+)\]")


def record_trajectory(  # noqa: PLR0913 — the seven ports the brief names, verbatim
    run_id: UUID,
    frame: str,
    *,
    runs: RunRepository,
    steps: StepRunRepository,
    attempts: AttemptRepository,
    gate_records: GateRecordRepository,
    git: Git | None,
    trajectories: TrajectoryRepository | None,
    clock: Clock,
) -> None:
    """Write one trajectory row for `frame`, or do nothing (AD-19, AD-6's replay safety).

    `trajectories is None` degrades like `tracer`/`spend_writes`: every fixture predating
    this story keeps working unchanged. A frame missing one of its three gated rows, or one
    whose `build`/`verify` have not actually finished, is left unrecorded rather than guessed
    at — the caller's own gate already makes this the ordinary case, never the observed one.
    """
    if trajectories is None:
        return
    run = runs.get(run_id)
    if run is None:
        return
    rows = rows_in_frame(steps.list_for_run(run_id), frame)
    build_row = _row(rows, AGENT_KIND)
    verify_row = _row(rows, SHELL_KIND)
    commit_row = _row(rows, COMMIT_KIND)
    if build_row is None or verify_row is None or commit_row is None:
        return
    if build_row.status != DONE or verify_row.status not in (DONE, SKIPPED):
        return
    build_attempts = attempts.list_for_row(build_row.id)
    records = gate_records.list_for_run(run_id)
    end_sha = _head_sha(git, run)
    trajectories.add(
        Trajectory(
            id=new_id(),
            run_id=run_id,
            project_id=run.project_id,
            repository_id=run.repository_id,
            story_id=build_row.story_id,
            epic_index=_epic_index(frame),
            frame=frame,
            harness=_latest(a.harness for a in reversed(build_attempts)),
            model=_latest(a.model for a in reversed(build_attempts)),
            attempts=tuple(_attempt_record(a) for a in build_attempts),
            gate_results=_gate_results(build_row, verify_row, commit_row, frame, records, run),
            cost_usd=_sum_cost(build_attempts),
            tokens_in=_sum_tokens(build_attempts, "tokens_in"),
            tokens_out=_sum_tokens(build_attempts, "tokens_out"),
            wall_clock_seconds=_wall_clock(build_attempts),
            story_file=_story_file(git, run, build_row, end_sha),
            start_sha=_latest(a.start_sha for a in build_attempts),
            end_sha=end_sha,
            human_actions=_human_actions(records, frame),
            recorded_at=clock.now(),
        )
    )


def _row(rows: list[StepRun], kind: str) -> StepRun | None:
    """The frame's one row of this kind, or `None` — every shipped Template has one."""
    return next((row for row in rows if row.kind == kind), None)


def _latest(values: Iterable[str | None]) -> str | None:
    """The first value that is not `None`/empty, in the order the caller hands them over."""
    return next((value for value in values if value), None)


def _epic_index(frame: str) -> int:
    """The `epics[n]` index this frame nests under, or `0` for a Run with no epic loop."""
    match = _EPIC_INDEX.search(frame)
    return int(match.group(1)) if match else 0


def _attempt_record(attempt: Attempt) -> AttemptRecord:
    return AttemptRecord(
        n=attempt.n,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        exit_code=attempt.exit_code,
        session_id=attempt.session_id,
        cost_usd=attempt.cost_usd,
        tokens_in=attempt.tokens_in,
        tokens_out=attempt.tokens_out,
        route=attempt.status,
    )


def _sum_cost(build_attempts: list[Attempt]) -> Decimal:
    return sum((a.cost_usd for a in build_attempts if a.cost_usd is not None), Decimal("0"))


def _sum_tokens(build_attempts: list[Attempt], field: str) -> int:
    return sum((getattr(a, field) or 0) for a in build_attempts)


def _wall_clock(build_attempts: list[Attempt]) -> float:
    total = 0.0
    for attempt in build_attempts:
        if attempt.started_at is not None and attempt.ended_at is not None:
            total += (attempt.ended_at - attempt.started_at).total_seconds()
    return total


def _gate_results(  # noqa: PLR0913, PLR0917 — the frame's three rows plus its records and Run
    build_row: StepRun,
    verify_row: StepRun,
    commit_row: StepRun,
    frame: str,
    records: list[GateRecord],
    run: Run,
) -> GateResults:
    hits = tuple(
        ProtectedPathHit(path=str(hit.get("path", "")), kind=str(hit.get("kind", "")))
        for entry in records
        if _in_frame_hit(entry, frame)
        for hit in entry.payload.get(HITS_KEY, [])
    )
    guard = NO_CHANGES if commit_row.reason == NO_CHANGES else DONE
    return GateResults(
        build=build_row.gate,
        verify=verify_row.status,
        commit_guard=guard,
        protected_paths=ProtectedPathsResult(hits=hits, accepted=run.accepted_paths),
    )


def _in_frame_hit(entry: GateRecord, frame: str) -> bool:
    return entry.event == PROTECTED_PATH and entry.path is not None and in_frame(entry.path, frame)


def _human_actions(records: list[GateRecord], frame: str) -> tuple[HumanAction, ...]:
    return tuple(
        HumanAction(event=entry.event, at=entry.at)
        for entry in records
        if entry.path is not None and in_frame(entry.path, frame) and entry.event in HUMAN_EVENTS
    )


def _head_sha(git: Git | None, run: Run) -> str | None:
    if git is None or not run.worktree_path:
        return None
    return git.head_sha(Path(run.worktree_path))


def _story_file(git: Git | None, run: Run, build_row: StepRun, end_sha: str | None) -> str:
    if git is None or end_sha is None or not run.worktree_path:
        return ""
    dest = Path(run.worktree_path)
    spec_folder = str(build_row.with_resolved.get(SPEC_FOLDER_KEY) or "")
    story_id = build_row.story_id or ""
    prefix = f"{spec_folder}/stories" if spec_folder else "stories"
    opening = f"{prefix}/{story_id}-"
    matches = [
        path
        for path in git.list_files(dest, end_sha, prefix)
        if path.startswith(opening) and path.endswith(".md")
    ]
    if not matches:
        return ""
    return git.read_file(dest, end_sha, matches[0]) or ""
