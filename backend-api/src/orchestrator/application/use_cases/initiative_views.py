"""The initiative list and detail reads (SPEC CAP-4; AD-36).

Every initiative is read with all its Runs, rows and attempts once; the status, attention and
step lines are computed from those, never stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from orchestrator.application.rules.initiative_lines import progress_line, step_line
from orchestrator.application.rules.initiative_status import (
    StatusReading,
    build_index,
    initiative_status,
)
from orchestrator.application.steps.context import WorkspaceFactory
from orchestrator.application.use_cases.initiative_detail_steps import (
    detail_runs,
    detail_workflows,
)
from orchestrator.application.use_cases.initiative_facts import (
    current_conversation_row,
    ended_turns,
    entry_steps,
    run_facts,
    session_turns,
    shown_indices,
    shown_number,
)
from orchestrator.application.use_cases.initiative_view_types import (
    Column,
    InitiativeDetail,
    InitiativeFilter,
    InitiativeList,
    InitiativeRow,
    ListCounts,
    Loaded,
    WorkflowFoot,
    WorkflowState,
)
from orchestrator.application.use_cases.run_views_board import board_current_step_label
from orchestrator.application.use_cases.run_views_summary import progress
from orchestrator.application.use_cases.walk_frame import row_workdir
from orchestrator.domain.entities.initiative import FrozenWorkflow, Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.initiative_runs import InitiativeRunReads
from orchestrator.domain.ports.initiatives import InitiativeAdvanceRepository, InitiativeRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)

__all__ = ["InitiativeReadPorts", "initiative_detail", "list_initiatives"]

RECENT_DAYS = 30


class _NoRun:
    """Stands for the latest Run of an initiative that has none, so `park_seq` is read, not
    computed: `test_park_record_invariant.py` flags any other write of that name."""

    park_seq = 0


@dataclass(frozen=True)
class InitiativeReadPorts:
    """What the initiative reads go through. Writes nothing."""

    initiatives: InitiativeRepository
    advances: InitiativeAdvanceRepository
    projects: ProjectRepository
    repositories: RepositoryRepository
    runs: RunRepository
    initiative_runs: InitiativeRunReads
    steps: StepRunRepository
    attempts: AttemptRepository
    git: Git
    workspace: WorkspaceFactory
    clock: Clock


def list_initiatives(
    ports: InitiativeReadPorts,
    *,
    project_id: UUID | None,
    filter: InitiativeFilter,
) -> InitiativeList:
    """Rows newest change first, narrowed by `filter`; `columns` and `counts` over the kept rows."""
    if project_id is not None and ports.projects.get(project_id) is None:
        raise NotFound(f"no project {project_id}")
    pairs = [
        (i, _row(ports, _load(ports, i))) for i in ports.initiatives.list(project_id=project_id)
    ]
    now = ports.clock.now()
    kept = [(i, row) for i, row in pairs if _kept(i, row, filter, now)]
    kept.sort(key=lambda pair: pair[1].updated_at, reverse=True)
    rows = [row for _, row in kept]
    return InitiativeList(items=rows, columns=_columns([i for i, _ in kept]), counts=_counts(rows))


def initiative_detail(ports: InitiativeReadPorts, initiative_id: UUID) -> InitiativeDetail:
    initiative = ports.initiatives.get(initiative_id)
    if initiative is None:
        raise NotFound(f"no initiative {initiative_id}")
    loaded = _load(ports, initiative)
    row = _row(ports, loaded)
    repository = ports.repositories.get(initiative.repository_id)
    folder = None if repository is None else f"{repository.initiative_folder}/{initiative.slug}/"
    latest = _latest(loaded.runs)
    stop = _NoRun if latest is None else latest
    return InitiativeDetail(
        row=row,
        first_message=initiative.first_message,
        round=initiative.round,
        created_at=initiative.created_at,
        cancelled_at=initiative.cancelled_at,
        branch_cleanup_error=initiative.branch_cleanup_error,
        pr_merged_at=initiative.pr_merged_at,
        package=initiative.sequence.package,
        sha=initiative.sequence.sha,
        park_seq=stop.park_seq,
        workflows=detail_workflows(loaded, ports.git, folder),
        runs=detail_runs(loaded),
    )


def _load(ports: InitiativeReadPorts, initiative: Initiative) -> Loaded:
    runs = ports.initiative_runs.list_for_initiative(initiative.id)
    rows = {run.id: ports.steps.list_for_run(run.id) for run in runs}
    attempts = {
        run.id: [a for row in rows[run.id] for a in ports.attempts.list_for_row(row.id)]
        for run in runs
    }
    facts = {
        run.id: run_facts(run, rows[run.id], attempts[run.id], ports.workspace) for run in runs
    }
    return Loaded(initiative, runs, rows, attempts, facts)


def _latest(runs: list[Run]) -> Run | None:
    return max(runs, key=lambda run: run.created_at, default=None)


def _kept(
    initiative: Initiative, row: InitiativeRow, kind: InitiativeFilter, now: datetime
) -> bool:
    if kind == "all":
        return True
    if kind == "needs_you":
        return row.status == "waiting for her"
    ended = {"done": initiative.pr_merged_at, "cancelled": initiative.cancelled_at}.get(row.status)
    return ended is None or now - ended <= timedelta(days=RECENT_DAYS)


def _columns(initiatives: list[Initiative]) -> list[Column]:
    columns: list[Column] = []
    for initiative in initiatives:
        for index in shown_indices(initiative.sequence):
            entry = initiative.sequence.workflows[index]
            if all(column.workflow != entry.workflow for column in columns):
                columns.append(Column(workflow=entry.workflow, type=entry.type))
    return columns


def _counts(rows: list[InitiativeRow]) -> ListCounts:
    waiting = [row for row in rows if row.status == "waiting for her"]
    return ListCounts(
        ongoing=sum(1 for row in rows if row.status in ("running", "waiting for her")),
        need_you=len(waiting),
        oldest_wait_at=min((row.updated_at for row in waiting), default=None),
        cancelled=sum(1 for row in rows if row.status == "cancelled"),
    )


def _row(ports: InitiativeReadPorts, loaded: Loaded) -> InitiativeRow:
    initiative = loaded.initiative
    reading = initiative_status(
        initiative,
        list(loaded.facts.values()),
        ports.advances.list_for_initiative(initiative.id),
        initiative.sequence.status_map,
    )
    latest = _latest(loaded.runs)
    position = None if latest is None else latest.initiative_position
    number = shown_number(initiative.sequence, position)
    indices = shown_indices(initiative.sequence)
    shown = [initiative.sequence.workflows[i] for i in indices]
    project = ports.projects.get(initiative.project_id)
    return InitiativeRow(
        id=initiative.id,
        project_id=initiative.project_id,
        project_name="" if project is None else project.name,
        repository_id=initiative.repository_id,
        repo_tag=_repo_tag(ports, loaded),
        slug=initiative.slug,
        name=initiative.name,
        status=reading.status,
        step=reading.step,
        reason=reading.reason,
        workflow=shown[number - 1].workflow,
        position=number,
        workflow_count=len(shown),
        workflows=_feet(shown, number, reading.status),
        line=_line(loaded, reading, latest),
        progress=_progress(loaded, reading, latest, indices[number - 1]),
        attention=None if latest is None else loaded.facts[latest.id].attention,
        updated_at=_updated_at(initiative, latest),
    )


def _updated_at(initiative: Initiative, latest: Run | None) -> datetime:
    own = initiative.updated_at or initiative.created_at
    if latest is None:
        return own
    return max(own, latest.updated_at or latest.created_at)


def _feet(shown: list[FrozenWorkflow], number: int, status: str) -> tuple[WorkflowFoot, ...]:
    def state(index: int) -> WorkflowState | None:
        if status == "done" or index < number:
            return "completed"
        if index == number and status != "cancelled":
            return "ongoing"
        return None

    return tuple(
        WorkflowFoot(entry.workflow, entry.type, state(n)) for n, entry in enumerate(shown, start=1)
    )


def _repo_tag(ports: InitiativeReadPorts, loaded: Loaded) -> tuple[str, ...]:
    index = build_index(loaded.initiative)
    builds = [run for run in loaded.runs if index is not None and run.initiative_position == index]
    build = _latest(builds)
    workdirs: list[str] = []
    for row in [] if build is None else loaded.rows[build.id]:
        workdir = row_workdir(row)
        if workdir and workdir not in workdirs:
            workdirs.append(workdir)
    if workdirs:
        return tuple(workdirs)
    hub = ports.repositories.get(loaded.initiative.repository_id)
    return () if hub is None else (hub.slug,)


def _line(loaded: Loaded, reading: StatusReading, latest: Run | None) -> str:
    row = None if latest is None else current_conversation_row(latest, loaded.rows[latest.id])
    turns = [] if row is None or latest is None else session_turns(row, loaded.attempts[latest.id])
    return step_line(
        loaded.initiative,
        reading,
        None if latest is None else loaded.facts[latest.id].attention,
        ended_turns=len(ended_turns(turns)),
        current_label=""
        if latest is None
        else board_current_step_label(latest, loaded.rows[latest.id]),
        harness=None if latest is None else latest.inputs.get("harness"),
    )


def _progress(loaded: Loaded, reading: StatusReading, latest: Run | None, index: int) -> str:
    sequence = loaded.initiative.sequence
    names = [name for name, _ in entry_steps(sequence, index)]
    step = names.index(reading.step) + 1 if reading.step in names else 1
    kind = sequence.workflows[index].type
    run_progress = None
    if kind == "auto" and latest is not None:
        run_progress = progress(latest, loaded.rows[latest.id])
    return progress_line(kind, k=step, j=len(names), run=latest, run_progress=run_progress)
