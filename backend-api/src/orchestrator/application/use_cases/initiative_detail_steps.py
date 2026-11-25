"""The steps of each shown workflow on the initiative page (SPEC "Shown workflows").

A `conversation` step reads its row in the latest Run holding one; the gate reads the
`spec-gate` row; a `shown_as: step` entry reads its own latest Run. Turns run across every
Run of the initiative, oldest Run first.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.use_cases.initiative_facts import (
    conversation_step,
    current_conversation_row,
    entry_steps,
    session_turns,
    shown_indices,
    shown_number,
)
from orchestrator.application.use_cases.initiative_view_types import (
    DetailRun,
    DetailStep,
    DetailWorkflow,
    InitiativeStepStatus,
    Loaded,
    StepFile,
    Turn,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import FrozenWorkflow
from orchestrator.domain.entities.project_package import StepDecl
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import Git, GitError

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


def detail_workflows(loaded: Loaded, git: Git, folder: str | None) -> list[DetailWorkflow]:
    sequence = loaded.initiative.sequence
    result: list[DetailWorkflow] = []
    for number, index in enumerate(shown_indices(sequence), start=1):
        entry = sequence.workflows[index]
        latest = _latest_at(loaded, index)
        steps = [
            _step(loaded, git, folder, index, entry, step_id, kind)
            for step_id, kind in entry_steps(sequence, index)
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
            position=shown_number(loaded.initiative.sequence, run.initiative_position),
            status=run.status,
            created_at=run.created_at,
        )
        for run in loaded.runs
    ]


def _latest_at(loaded: Loaded, index: int) -> Run | None:
    at = [run for run in loaded.runs if run.initiative_position == index]
    return max(at, key=lambda run: run.created_at, default=None)


def _step(  # noqa: PLR0913, PLR0917 — one fact per argument, read once by the caller
    loaded: Loaded,
    git: Git,
    folder: str | None,
    index: int,
    entry: FrozenWorkflow,
    step_id: str,
    kind: str,
) -> DetailStep:
    decl = next((d for d in entry.steps if d.id == step_id), None)
    if decl is None:
        return _merge_step(loaded, step_id)
    if kind == CONVERSATION_KIND:
        return _conversation(loaded, git, folder, index, decl.id, decl)
    return _gate(loaded, index, decl)


def _merge_step(loaded: Loaded, workflow: str) -> DetailStep:
    sequence = loaded.initiative.sequence
    index = next(i for i, e in enumerate(sequence.workflows) if e.workflow == workflow)
    latest = _latest_at(loaded, index)
    return DetailStep(
        id=workflow,
        kind="automatic",
        persona=None,
        skill=None,
        file=None,
        status="planned" if latest is None else _RUN_STATUS[latest.status],
        line="" if latest is None else latest.park_reason or "",
        turns=[],
        files=[],
    )


def _row_status(
    row: StepRun | None, run: Run | None, loaded: Loaded, *, mapped: bool
) -> InitiativeStepStatus:
    if row is None or run is None:
        return "planned"
    facts = loaded.facts[run.id]
    if mapped and run.status == "running" and _is_current(run, row, loaded):
        word = facts.step_word
        status_map: Mapping[str, str] = loaded.initiative.sequence.status_map
        if word is not None and word in status_map:
            return status_map[word]  # type: ignore[return-value]
    if row.status == "checkpoint":
        return "waiting for her" if facts.attention == "blocked" else "running"
    return _ROW_STATUS.get(row.status, "planned")


def _is_current(run: Run, row: StepRun, loaded: Loaded) -> bool:
    current = current_conversation_row(run, loaded.rows[run.id])
    return current is not None and current.id == row.id


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


def _gate(loaded: Loaded, index: int, decl: StepDecl) -> DetailStep:
    run, row = _holders(loaded, index, lambda r: r.role == GATE_ROLE)
    return DetailStep(
        id=decl.id,
        kind=decl.kind,
        persona=decl.persona,
        skill=decl.skill,
        file=decl.file,
        status=_row_status(row, run, loaded, mapped=False),
        line="" if row is None else row.reason or "",
        turns=[],
        files=[],
    )


def _conversation(  # noqa: PLR0913, PLR0917 — one fact per argument
    loaded: Loaded, git: Git, folder: str | None, index: int, step_id: str, decl: StepDecl
) -> DetailStep:
    run, row = _holders(
        loaded,
        index,
        lambda r: r.kind == CONVERSATION_KIND and conversation_step(r) == step_id,
    )
    status = _row_status(row, run, loaded, mapped=True)
    by_run = _turns_by_run(loaded, step_id)
    turns = [_turn(run_, a) for run_, attempts in by_run for a in attempts]
    return DetailStep(
        id=decl.id,
        kind=decl.kind,
        persona=decl.persona,
        skill=decl.skill,
        file=decl.file,
        status=status,
        line="" if row is None else row.reason or "",
        turns=turns,
        files=_files(by_run, git, folder, draft=status != "done"),
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


def _turn(run: Run, attempt: Attempt) -> Turn:
    return Turn(
        attempt_id=attempt.id,
        run_id=run.id,
        round=run.initiative_round or 1,
        n=attempt.n,
        status=attempt.status,
        message=attempt.message,
        reply=attempt.reply,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
    )


def _files(
    by_run: list[tuple[Run, list[Attempt]]],
    git: Git,
    folder: str | None,
    *,
    draft: bool,
) -> list[StepFile]:
    paths: list[str] = []
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
            if change.path.startswith(folder) and change.path not in paths:
                paths.append(change.path)
    return [StepFile(path=path, draft=draft) for path in paths]
