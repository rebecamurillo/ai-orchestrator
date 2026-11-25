"""The initiative detail's steps, turns, files and lists (`GET /initiatives/{id}`, SPEC CAP-6)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.use_cases.initiative_view_types import (
    DetailStep,
    DetailWorkflow,
    FilesState,
    HubRef,
    InitiativeStepStatus,
    ProjectRef,
    SessionEntry,
    StepFile,
    StepToken,
    Turn,
    TurnStatus,
    WorkflowFile,
)
from orchestrator.domain.statuses import ParkKind, RunStatus


class ProjectRefOut(BaseModel):
    id: UUID
    name: str

    @classmethod
    def of(cls, ref: ProjectRef) -> ProjectRefOut:
        return cls(id=ref.id, name=ref.name)


class HubRefOut(BaseModel):
    id: UUID
    slug: str

    @classmethod
    def of(cls, ref: HubRef) -> HubRefOut:
        return cls(id=ref.id, slug=ref.slug)


class WorkflowFileOut(BaseModel):
    path: str
    run_id: UUID

    @classmethod
    def of(cls, file: WorkflowFile) -> WorkflowFileOut:
        return cls(path=file.path, run_id=file.run_id)


class SessionEntryOut(BaseModel):
    workflow: str
    step: str | None
    kind: Literal["session", "run"]
    id: UUID
    round: int
    state: str

    @classmethod
    def of(cls, entry: SessionEntry) -> SessionEntryOut:
        return cls(
            workflow=entry.workflow,
            step=entry.step,
            kind=entry.kind,
            id=entry.id,
            round=entry.round,
            state=entry.state,
        )


class TurnOut(BaseModel):
    attempt_id: UUID
    run_id: UUID
    round: int
    n: int
    status: TurnStatus
    author: Literal["operator", "gate"]
    message: str
    reply: str
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None
    defects: int | None
    owner: str | None
    model: str | None
    failure_reason: str | None

    @classmethod
    def of(cls, turn: Turn) -> TurnOut:
        return cls(
            attempt_id=turn.attempt_id,
            run_id=turn.run_id,
            round=turn.round,
            n=turn.n,
            status=turn.status,
            message=turn.message,
            reply=turn.reply,
            started_at=turn.started_at,
            ended_at=turn.ended_at,
            author=turn.author,
            defects=turn.defects,
            owner=turn.owner,
            model=turn.model,
            failure_reason=turn.failure_reason,
        )


class StepFileOut(BaseModel):
    path: str
    draft: bool
    run_id: UUID | None
    time: UtcTimestamp | None
    changed: bool

    @classmethod
    def of(cls, file: StepFile) -> StepFileOut:
        return cls(
            path=file.path,
            draft=file.draft,
            run_id=file.run_id,
            time=file.time,
            changed=file.changed,
        )


class DetailStepOut(BaseModel):
    id: str
    kind: Literal["conversation", "automatic"]
    persona: str | None
    skill: str | None
    file: str | None
    status: InitiativeStepStatus
    line: str
    turns: list[TurnOut]
    files: list[StepFileOut]
    number: str
    agent: str | None
    harness: str | None
    model: str | None
    run_id: UUID | None
    park_seq: int | None
    park_kind: ParkKind | None
    park_reason: str | None
    token: StepToken
    files_state: FilesState
    conflict_files: list[str]

    @classmethod
    def of(cls, step: DetailStep) -> DetailStepOut:
        return cls(
            id=step.id,
            kind=step.kind,  # type: ignore[arg-type]
            persona=step.persona,
            skill=step.skill,
            file=step.file,
            status=step.status,
            line=step.line,
            turns=[TurnOut.of(turn) for turn in step.turns],
            files=[StepFileOut.of(file) for file in step.files],
            number=step.number,
            agent=step.agent,
            harness=step.harness,
            model=step.model,
            run_id=step.run_id,
            park_seq=step.park_seq,
            park_kind=step.park_kind,
            park_reason=step.park_reason,
            token=step.token,
            files_state=step.files_state,
            conflict_files=list(step.conflict_files),
        )


class DetailWorkflowOut(BaseModel):
    position: int
    workflow: str
    template: str
    version: int
    type: str
    status: RunStatus | None
    run_id: UUID | None
    steps: list[DetailStepOut]
    line: str
    files: list[WorkflowFileOut]

    @classmethod
    def of(cls, workflow: DetailWorkflow) -> DetailWorkflowOut:
        return cls(
            position=workflow.position,
            workflow=workflow.workflow,
            template=workflow.template,
            version=workflow.version,
            type=workflow.type,
            status=workflow.status,
            run_id=workflow.run_id,
            steps=[DetailStepOut.of(step) for step in workflow.steps],
            line=workflow.line,
            files=[WorkflowFileOut.of(file) for file in workflow.files],
        )
