"""The steps of each shown workflow on the initiative page (SPEC "Shown workflows").

A `conversation` step reads its row in the latest Run holding one; the gate reads the
`spec-gate` row; a `shown_as: step` entry reads its own latest Run. Turns run across every
Run of the initiative, oldest Run first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from uuid import UUID

from orchestrator.application.rules.initiative_lines import (
    files_state,
)
from orchestrator.application.rules.initiative_transitions import defect_count
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.use_cases.initiative_detail_lines import (
    At,
    MergeFact,
    StepContext,
    at_of,
    auto_files_of,
    facts_of,
    is_current,
    strip_of,
    token_of,
    track_line,
)
from orchestrator.application.use_cases.initiative_facts import (
    conversation_step,
    entry_steps,
    session_turns,
    shown_indices,
)
from orchestrator.application.use_cases.initiative_gate_turns import gate_turns
from orchestrator.application.use_cases.initiative_reopen_mark import ReopenMark, reopen_mark
from orchestrator.application.use_cases.initiative_step_parts import (
    conflicts_of,
    forced,
    step_number,
    timed_files,
    turn_status,
)
from orchestrator.application.use_cases.initiative_view_types import (
    DetailRun,
    DetailStep,
    DetailWorkflow,
    InitiativeStepStatus,
    Loaded,
    ReopenedAfter,
    Turn,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import FrozenWorkflow
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun

GATE_ROLE = "spec-gate"

_ROW_STATUS: dict[str, InitiativeStepStatus] = {
    "done": "done",
    "skipped": "skipped",
    "running": "running",
    "queued": "running",
    "error": "failed",
    "blocked": "failed",
}
_RUN_STATUS: dict[str, InitiativeStepStatus] = {
    "queued": "running",
    "running": "running",
    "needs_you": "waiting for her",
    "done": "done",
    "failed": "failed",
    "cancelled": "failed",
}


def detail_workflows(ctx: StepContext) -> list[DetailWorkflow]:
    loaded = ctx.loaded
    sequence = loaded.initiative.sequence
    result: list[DetailWorkflow] = []
    names = [sequence.workflows[i].workflow for i in shown_indices(sequence)]
    mark = reopen_mark(loaded)
    for number, index in enumerate(shown_indices(sequence), start=1):
        entry = sequence.workflows[index]
        latest = _latest_at(loaded, index)
        listed = entry_steps(sequence, index)
        steps = [
            _step(ctx, entry, at_of(ctx, entry, index, number, listed, k), step_id, kind, mark)
            for k, (step_id, kind) in enumerate(listed, start=1)
        ]
        result.append(
            DetailWorkflow(
                position=number,
                workflow=entry.workflow,
                template=entry.template,
                version=entry.version,
                type=entry.type,
                status=None if latest is None else latest.status,
                run_id=None if latest is None else latest.id,
                steps=steps,
                line=_stopped_line(mark)
                if mark is not None and mark.auto_index == index
                else track_line(ctx, entry, number, index, listed, names),
                files=auto_files_of(ctx, entry, latest),
                token="BLK" if mark is not None and mark.auto_index == index else None,
            )
        )
    return result


def detail_runs(loaded: Loaded) -> list[DetailRun]:
    return [
        DetailRun(
            id=run.id,
            template_name=run.template_name,
            template_version=run.template_version,
            round=run.initiative_round or 1,
            position=run.initiative_position or 0,
            status=run.status,
            created_at=run.created_at,
        )
        for run in loaded.runs
    ]


def _latest_at(loaded: Loaded, index: int) -> Run | None:
    at = [run for run in loaded.runs if run.initiative_position == index]
    return max(at, key=lambda run: run.created_at, default=None)


def _stopped_line(mark: ReopenMark) -> str:
    return f"stopped on the spec · {mark.step} reopens"


def _step(  # noqa: PLR0913, PLR0917 — one fact per argument
    ctx: StepContext,
    entry: FrozenWorkflow,
    at: At,
    step_id: str,
    kind: str,
    mark: ReopenMark | None,
) -> DetailStep:
    decl = next((d for d in entry.steps if d.id == step_id), None)
    if decl is None:
        return _merge_step(ctx, step_id, at, mark)
    if kind == CONVERSATION_KIND:
        step = _conversation(ctx, at, decl)
        if mark is None or mark.step != decl.id:
            return step
        return replace(step, reopened_after=ReopenedAfter(mark.workflow, mark.branch))
    return _gate(ctx, at, decl)


def _merge_step(ctx: StepContext, workflow: str, at: At, mark: ReopenMark | None) -> DetailStep:
    loaded = ctx.loaded
    sequence = loaded.initiative.sequence
    index = next(i for i, e in enumerate(sequence.workflows) if e.workflow == workflow)
    latest = _latest_at(loaded, index)
    status: InitiativeStepStatus = "planned" if latest is None else _RUN_STATUS[latest.status]
    conflicts = (
        []
        if latest is None
        else conflicts_of(latest, loaded.rows[latest.id], loaded.attempts[latest.id])
    )
    line = strip_of(
        ctx,
        at,
        status=status,
        kind="automatic",
        run=latest,
        row=None,
        turns=[],
        files=[],
        merge=MergeFact(len(conflicts), None if latest is None else latest.park_reason),
    )
    stopped = mark is not None and mark.workflow == workflow
    return DetailStep(
        id=workflow,
        kind="automatic",
        persona=None,
        skill=None,
        file=None,
        status=status,
        line=_stopped_line(mark) if stopped and mark is not None else line,
        turns=[],
        files=[],
        number=step_number(at.number, at.k),
        token="BLK" if stopped else token_of(ctx, status, None),
        files_state=files_state(status, forced=False),
        conflict_files=conflicts,
        **facts_of(ctx, latest, None, None),
    )


def _row_status(
    row: StepRun | None, run: Run | None, loaded: Loaded, *, mapped: bool
) -> InitiativeStepStatus:
    if row is None or run is None:
        return "planned"
    facts = loaded.facts[run.id]
    if mapped and run.status == "running" and is_current(run, row, loaded):
        word = facts.step_word
        status_map: Mapping[str, str] = loaded.initiative.sequence.status_map
        if word is not None and word in status_map:
            return status_map[word]  # type: ignore[return-value]
    if row.status == "checkpoint":
        return "waiting for her" if facts.attention == "blocked" else "running"
    return _ROW_STATUS.get(row.status, "planned")


def _holders(loaded: Loaded, index: int, match: object) -> tuple[Run | None, StepRun | None]:
    """The latest Run at `index` holding a row `match` accepts, and that row."""
    found: tuple[Run | None, StepRun | None] = (None, None)
    for run in sorted(
        (r for r in loaded.runs if r.initiative_position == index), key=lambda r: r.created_at
    ):
        row = next((r for r in loaded.rows[run.id] if match(r)), None)  # type: ignore[operator]
        if row is not None:
            found = (run, row)
    return found


def _gate(ctx: StepContext, at: At, decl: StepDecl) -> DetailStep:
    loaded = ctx.loaded
    run, row = _holders(loaded, at.index, lambda r: r.role == GATE_ROLE)
    status = _row_status(row, run, loaded, mapped=False)
    line = strip_of(ctx, at, status=status, kind="automatic", run=run, row=row, turns=[], files=[])
    return DetailStep(
        id=decl.id,
        kind=decl.kind,
        persona=decl.persona,
        skill=decl.skill,
        file=decl.file,
        status=status,
        line=line,
        turns=[],
        files=[],
        number=step_number(at.number, at.k),
        token=token_of(ctx, status, row),
        files_state=files_state(status, forced=forced(row)),
        **facts_of(ctx, run, row, decl),
    )


def _conversation(ctx: StepContext, at: At, decl: StepDecl) -> DetailStep:
    loaded = ctx.loaded
    run, row = _holders(
        loaded,
        at.index,
        lambda r: r.kind == CONVERSATION_KIND and conversation_step(r) == decl.id,
    )
    status = _row_status(row, run, loaded, mapped=True)
    by_run = _turns_by_run(loaded, decl.id)
    gate = gate_turns(loaded)
    turns = [_turn(run_, a, gate) for run_, attempts in by_run for a in attempts]
    files = timed_files(by_run, ctx.git, ctx.folder, draft=status != "done", prior=ctx.prior)
    holder = [a for r, attempts in by_run if run is not None and r.id == run.id for a in attempts]
    line = strip_of(
        ctx, at, status=status, kind="conversation", run=run, row=row, turns=holder, files=files
    )
    return DetailStep(
        id=decl.id,
        kind=decl.kind,
        persona=decl.persona,
        skill=decl.skill,
        file=decl.file,
        status=status,
        line=line,
        turns=turns,
        files=files,
        number=step_number(at.number, at.k),
        token=token_of(ctx, status, row),
        files_state=files_state(status, forced=forced(row)),
        **facts_of(ctx, run, row, decl),
    )


def _turns_by_run(loaded: Loaded, step_id: str) -> list[tuple[Run, list[Attempt]]]:
    grouped: list[tuple[Run, list[Attempt]]] = []
    for run in sorted(loaded.runs, key=lambda r: r.created_at):
        attempts: list[Attempt] = []
        for row in loaded.rows[run.id]:
            if row.kind == CONVERSATION_KIND and conversation_step(row) == step_id:
                attempts.extend(session_turns(row, loaded.attempts[run.id]))
        if attempts:
            grouped.append((run, sorted(attempts, key=lambda a: a.n)))
    return grouped


def _turn(run: Run, attempt: Attempt, gate: Mapping[UUID, str]) -> Turn:
    status = turn_status(attempt)
    from_gate = attempt.id in gate
    return Turn(
        attempt_id=attempt.id,
        run_id=run.id,
        round=run.initiative_round or 1,
        n=attempt.n,
        status=status,
        message=attempt.message,
        reply=attempt.reply,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        model=attempt.model,
        failure_reason=attempt.output_ref if status == "failed" else None,
        author="gate" if from_gate else "operator",
        defects=defect_count(attempt.message) if from_gate else None,
        owner=gate.get(attempt.id),
    )
