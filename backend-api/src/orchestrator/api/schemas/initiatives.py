"""The initiative list and detail wire shapes (`GET /initiatives`, `GET /initiatives/{id}`)."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import UtcTimestamp
from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import InitiativeStatusValue
from orchestrator.application.use_cases.initiative_view_types import (
    Column,
    DetailRun,
    DetailStep,
    DetailWorkflow,
    InitiativeDetail,
    InitiativeList,
    InitiativeRow,
    InitiativeStepStatus,
    ListCounts,
    StepFile,
    Turn,
    WorkflowFoot,
    WorkflowState,
)
from orchestrator.domain.statuses import RunStatus, StepStatus


class ColumnOut(BaseModel):
    workflow: str
    type: str

    @classmethod
    def of(cls, column: Column) -> ColumnOut:
        return cls(workflow=column.workflow, type=column.type)


class WorkflowFootOut(BaseModel):
    workflow: str
    type: str
    state: WorkflowState | None

    @classmethod
    def of(cls, foot: WorkflowFoot) -> WorkflowFootOut:
        return cls(workflow=foot.workflow, type=foot.type, state=foot.state)


class ListCountsOut(BaseModel):
    ongoing: int
    need_you: int
    oldest_wait_at: UtcTimestamp | None
    cancelled: int

    @classmethod
    def of(cls, counts: ListCounts) -> ListCountsOut:
        return cls(
            ongoing=counts.ongoing,
            need_you=counts.need_you,
            oldest_wait_at=counts.oldest_wait_at,
            cancelled=counts.cancelled,
        )


class RowCoreOut(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    repository_id: UUID
    repo_tag: list[str]
    slug: str
    name: str
    status: InitiativeStatusValue
    step: str
    reason: str
    workflow: str
    position: int
    workflow_count: int
    line: str
    progress: str
    attention: Attention | None
    updated_at: UtcTimestamp


def _core(row: InitiativeRow) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "project_name": row.project_name,
        "repository_id": row.repository_id,
        "repo_tag": list(row.repo_tag),
        "slug": row.slug,
        "name": row.name,
        "status": row.status,
        "step": row.step,
        "reason": row.reason,
        "workflow": row.workflow,
        "position": row.position,
        "workflow_count": row.workflow_count,
        "line": row.line,
        "progress": row.progress,
        "attention": row.attention,
        "updated_at": row.updated_at,
    }


class InitiativeRowOut(RowCoreOut):
    workflows: list[WorkflowFootOut]

    @classmethod
    def of(cls, row: InitiativeRow) -> InitiativeRowOut:
        return cls(**_core(row), workflows=[WorkflowFootOut.of(foot) for foot in row.workflows])  # type: ignore[arg-type]


class InitiativeListOut(BaseModel):
    """`GET /initiatives`: rows, the shown workflows as columns, and the counts."""

    items: list[InitiativeRowOut]
    columns: list[ColumnOut]
    counts: ListCountsOut
    next_cursor: str | None = None

    @classmethod
    def of(cls, view: InitiativeList) -> InitiativeListOut:
        return cls(
            items=[InitiativeRowOut.of(row) for row in view.items],
            columns=[ColumnOut.of(column) for column in view.columns],
            counts=ListCountsOut.of(view.counts),
        )


class TurnOut(BaseModel):
    attempt_id: UUID
    run_id: UUID
    round: int
    n: int
    status: StepStatus
    message: str
    reply: str
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None

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
        )


class StepFileOut(BaseModel):
    path: str
    draft: bool

    @classmethod
    def of(cls, file: StepFile) -> StepFileOut:
        return cls(path=file.path, draft=file.draft)


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
        )


class DetailRunOut(BaseModel):
    id: UUID
    template_name: str
    template_version: int
    round: int
    position: int
    status: RunStatus
    created_at: UtcTimestamp

    @classmethod
    def of(cls, run: DetailRun) -> DetailRunOut:
        return cls(
            id=run.id,
            template_name=run.template_name,
            template_version=run.template_version,
            round=run.round,
            position=run.position,
            status=run.status,
            created_at=run.created_at,
        )


class InitiativeDetailOut(RowCoreOut):
    """`GET /initiatives/{id}`: the row's fields, with `workflows` carrying steps and Runs."""

    workflows: list[DetailWorkflowOut]
    first_message: str
    round: int
    created_at: UtcTimestamp
    cancelled_at: UtcTimestamp | None
    branch_cleanup_error: str | None
    pr_merged_at: UtcTimestamp | None
    package: str
    sha: str
    park_seq: int
    runs: list[DetailRunOut]

    @classmethod
    def of(cls, detail: InitiativeDetail) -> InitiativeDetailOut:
        return cls(
            **_core(detail.row),  # type: ignore[arg-type]
            workflows=[DetailWorkflowOut.of(w) for w in detail.workflows],
            first_message=detail.first_message,
            round=detail.round,
            created_at=detail.created_at,
            cancelled_at=detail.cancelled_at,
            branch_cleanup_error=detail.branch_cleanup_error,
            pr_merged_at=detail.pr_merged_at,
            package=detail.package,
            sha=detail.sha,
            park_seq=detail.park_seq,
            runs=[DetailRunOut.of(run) for run in detail.runs],
        )
