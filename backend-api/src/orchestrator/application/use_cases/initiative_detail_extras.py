"""The header and the lists of the initiative detail (story 6, epic 7).

Pure over what `initiative_views` already read; `auto_files` is the one read that goes further,
through `files_by_epic`.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from orchestrator.application.rules import conversation, session
from orchestrator.application.rules.signals import row_at
from orchestrator.application.steps import CONVERSATION_KIND
from orchestrator.application.use_cases.initiative_facts import conversation_step
from orchestrator.application.use_cases.initiative_view_types import (
    HubRef,
    Loaded,
    ProjectRef,
    SessionEntry,
    WorkflowFile,
)
from orchestrator.application.use_cases.run_files_by_epic import FilesByEpicPorts, files_by_epic
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.repositories import ProjectRepository
from orchestrator.domain.statuses import TERMINAL_RUN


def project_ref(projects: ProjectRepository, initiative: Initiative) -> ProjectRef | None:
    project = projects.get(initiative.project_id)
    return None if project is None else ProjectRef(id=project.id, name=project.name)


def hub_ref(repository: Repository | None) -> HubRef | None:
    return None if repository is None else HubRef(id=repository.id, slug=repository.slug)


def current_step(loaded: Loaded, latest: Run | None) -> str | None:
    """The conversation step the latest Run is on, else the `shown_as: step` entry it runs."""
    if latest is None:
        return None
    step = loaded.facts[latest.id].step
    if step:
        return step
    workflows = loaded.initiative.sequence.workflows
    position = latest.initiative_position
    if position is not None and 0 <= position < len(workflows):
        entry = workflows[position]
        if entry.shown_as == "step":
            return entry.workflow
    return None


def owners(loaded: Loaded) -> list[str]:
    """The `round_steps` of the latest Run at the spec workflow, in order."""
    workflows = loaded.initiative.sequence.workflows
    spec = next(
        (i for i, e in enumerate(workflows) if any(s.kind == CONVERSATION_KIND for s in e.steps)),
        None,
    )
    at = [run for run in loaded.runs if spec is not None and run.initiative_position == spec]
    latest = max(at, key=lambda run: run.created_at, default=None)
    return [] if latest is None else list(conversation.round_list(latest.inputs))


def sessions(loaded: Loaded) -> list[SessionEntry]:
    """One entry per step session and per Run, in creation order, a Run before its sessions."""
    workflows = loaded.initiative.sequence.workflows
    timed: list[tuple[datetime, int, SessionEntry]] = []
    for run in loaded.runs:
        position = run.initiative_position
        name = (
            ""
            if position is None or not 0 <= position < len(workflows)
            else (workflows[position].workflow)
        )
        round_ = run.initiative_round or 1
        timed.append(
            (run.created_at, 0, SessionEntry(name, None, "run", run.id, round_, run.status))
        )
        started = [
            r
            for r in loaded.records.get(run.id, [])
            if r.event == session.SESSION_START
            and r.payload.get(session.SCOPE_KEY) == session.STEP_SCOPE
        ]
        for record in started:
            row = row_at(loaded.rows[run.id], record.path)
            step = (
                conversation_step(row)
                if row is not None and row.kind == CONVERSATION_KIND
                else name
            )
            live = record is started[-1] and run.senior_session and run.status not in TERMINAL_RUN
            state = "open" if live else "closed"
            timed.append(
                (record.at, 1, SessionEntry(name, step, "session", record.id, round_, state))
            )
    timed.sort(key=lambda item: (item[0], item[1]))
    return [entry for _, _, entry in timed]


def auto_files(ports: FilesByEpicPorts | None) -> Callable[[UUID], list[WorkflowFile]] | None:
    """`(run_id) -> files`: every story file `files_by_epic` lists, first seen first."""
    if ports is None:
        return None

    def files(run_id: UUID) -> list[WorkflowFile]:
        found: list[WorkflowFile] = []
        for epic in files_by_epic(ports, run_id):
            for story in epic.stories:
                path = story.story_file
                if path and all(f.path != path for f in found):
                    found.append(WorkflowFile(path=path, run_id=run_id))
        return found

    return files
