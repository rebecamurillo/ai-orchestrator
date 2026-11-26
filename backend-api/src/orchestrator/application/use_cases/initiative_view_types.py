"""The initiative read model's dataclasses (AD-36; SPEC CAP-4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from orchestrator.application.rules.attention import Attention
from orchestrator.application.rules.initiative_status import InitiativeStatusValue, RunFacts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.statuses import ParkKind, RunStatus

InitiativeFilter = Literal["ongoing", "needs_you", "all"]
InitiativeStepStatus = Literal["planned", "running", "waiting for her", "done", "skipped", "failed"]
WorkflowState = Literal["completed", "ongoing"]
TurnStatus = Literal["queued", "running", "done", "failed"]
FilesState = Literal["done", "open", "to come", "skipped, forced", "failed"]
StepToken = Literal["RUN", "BLK", "DON", "ERR", "CAN", "QUE", "SKP"]


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
    status: TurnStatus
    message: str
    reply: str
    started_at: datetime | None
    ended_at: datetime | None
    author: Literal["operator", "gate"] = "operator"
    defects: int | None = None
    owner: str | None = None
    model: str | None = None
    failure_reason: str | None = None


@dataclass(frozen=True)
class StepFile:
    path: str
    draft: bool
    run_id: UUID | None = None
    time: datetime | None = None
    changed: bool = False


@dataclass(frozen=True)
class ProjectRef:
    id: UUID
    name: str


@dataclass(frozen=True)
class HubRef:
    id: UUID
    slug: str


@dataclass(frozen=True)
class WorkflowFile:
    path: str
    run_id: UUID


@dataclass(frozen=True)
class SessionEntry:
    workflow: str
    step: str | None
    kind: Literal["session", "run"]
    id: UUID
    round: int
    state: str


@dataclass(frozen=True)
class PriorView:
    """The `last_opened_at` a read found before it wrote a new one."""

    at: datetime | None


@dataclass(frozen=True)
class ReopenedAfter:
    """The `auto` workflow a reopen cancelled, and whether the reopen made or found the branch."""

    workflow: str
    branch: Literal["created", "attached"]


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
    number: str = ""
    agent: str | None = None
    harness: str | None = None
    model: str | None = None
    run_id: UUID | None = None
    park_seq: int | None = None
    park_kind: ParkKind | None = None
    park_reason: str | None = None
    token: StepToken = "QUE"
    files_state: FilesState = "to come"
    conflict_files: list[str] = field(default_factory=list)
    reopened_after: ReopenedAfter | None = None


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
    line: str = ""
    files: list[WorkflowFile] = field(default_factory=list)
    token: StepToken | None = None


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
    project: ProjectRef | None = None
    hub: HubRef | None = None
    folder: str = ""
    workflow_count: int = 0
    sequence_fixed_at: datetime | None = None
    current_position: int = 1
    current_step: str | None = None
    last_opened_at: datetime | None = None
    owners: list[str] = field(default_factory=list)
    sessions: list[SessionEntry] = field(default_factory=list)


@dataclass(frozen=True)
class Loaded:
    """One initiative with every Run, row and attempt it owns, each read once."""

    initiative: Initiative
    runs: list[Run]
    rows: dict[UUID, list[StepRun]]
    attempts: dict[UUID, list[Attempt]]
    facts: dict[UUID, RunFacts]
    records: dict[UUID, list[GateRecord]] = field(default_factory=dict)
