"""The initiative read model's dataclasses (AD-36; SPEC CAP-4)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import InitiativeStatusValue, RunFacts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import RunStatus, StepStatus

InitiativeFilter = Literal["ongoing", "needs_you", "all"]
InitiativeStepStatus = Literal["planned", "running", "waiting for her", "done", "skipped", "failed"]
WorkflowState = Literal["completed", "ongoing"]


@dataclass(frozen=True)
class InitiativeTag:
    """Which initiative, and where in its sequence, a Run belongs."""

    id: UUID
    slug: str
    step: str | None
    position: int
    workflow_count: int


@dataclass(frozen=True)
class Column:
    workflow: str
    type: str


@dataclass(frozen=True)
class WorkflowFoot:
    workflow: str
    type: str
    state: WorkflowState | None


@dataclass(frozen=True)
class ListCounts:
    ongoing: int
    need_you: int
    oldest_wait_at: datetime | None
    cancelled: int


@dataclass(frozen=True)
class InitiativeRow:
    id: UUID
    project_id: UUID
    project_name: str
    repository_id: UUID
    repo_tag: tuple[str, ...]
    slug: str
    name: str
    status: InitiativeStatusValue
    step: str
    reason: str
    workflow: str
    position: int
    workflow_count: int
    workflows: tuple[WorkflowFoot, ...]
    line: str
    progress: str
    attention: Attention | None
    updated_at: datetime


@dataclass(frozen=True)
class InitiativeList:
    items: list[InitiativeRow]
    columns: list[Column]
    counts: ListCounts


@dataclass(frozen=True)
class Turn:
    attempt_id: UUID
    run_id: UUID
    round: int
    n: int
    status: StepStatus
    message: str
    reply: str
    started_at: datetime | None
    ended_at: datetime | None


@dataclass(frozen=True)
class StepFile:
    path: str
    draft: bool


@dataclass(frozen=True)
class DetailStep:
    id: str
    kind: str
    persona: str | None
    skill: str | None
    file: str | None
    status: InitiativeStepStatus
    line: str
    turns: list[Turn]
    files: list[StepFile]


@dataclass(frozen=True)
class DetailWorkflow:
    position: int
    workflow: str
    template: str
    version: int
    type: str
    status: RunStatus | None
    run_id: UUID | None
    steps: list[DetailStep]


@dataclass(frozen=True)
class DetailRun:
    id: UUID
    template_name: str
    template_version: int
    round: int
    position: int
    status: RunStatus
    created_at: datetime


@dataclass(frozen=True)
class InitiativeDetail:
    row: InitiativeRow
    first_message: str
    round: int
    created_at: datetime
    cancelled_at: datetime | None
    branch_cleanup_error: str | None
    pr_merged_at: datetime | None
    package: str
    sha: str
    park_seq: int
    workflows: list[DetailWorkflow]
    runs: list[DetailRun]


@dataclass(frozen=True)
class Loaded:
    """One initiative with every Run, row and attempt it owns, each read once."""

    initiative: Initiative
    runs: list[Run]
    rows: dict[UUID, list[StepRun]]
    attempts: dict[UUID, list[Attempt]]
    facts: dict[UUID, RunFacts]
