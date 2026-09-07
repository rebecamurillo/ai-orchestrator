"""The Board's and the Run detail's own dataclasses (SPEC CAP-12, FR-22, FR-23, FR-28).

Split out of `application/use_cases/run_views.py` on line count alone (`backend-api/
AGENTS.md`'s 400-line module limit) — the pure builders (`board_view`, `run_detail`) and
every private helper stay there; only the shapes they build live here, the same split
`application/graph.py`/`graph_schema.py` uses for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.logs import LogReader
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.statuses import ParkKind, RunStatus, SignalKind


@dataclass(frozen=True)
class RunViewPorts:
    """What the Run detail and the run graph route both read through. Writes nothing."""

    runs: RunRepository
    steps: StepRunRepository
    attempts: AttemptRepository
    gate_records: GateRecordRepository
    projects: ProjectRepository
    repositories: RepositoryRepository
    logs: LogReader
    clock: Clock


@dataclass(frozen=True)
class Progress:
    """Epic/story completion (SPEC CAP-12); `epics_*` is `None` outside an `initiative` Run."""

    epics_done: int | None
    epics_total: int | None
    stories_done: int
    stories_total: int
    links: int


# ── the Board (SPEC CAP-12, CAP-14) ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class Card:
    """One box on the Board — every field a column, a token, or a progress bar needs."""

    id: UUID
    token: str
    status: RunStatus
    park_kind: ParkKind | None
    branch: str
    project_name: str
    repository_slug: str
    current_step_label: str
    harness: str | None
    template: str
    version: int
    progress: Progress | None
    kind_label: str | None
    age_seconds: float
    needs_you_since: datetime | None


@dataclass(frozen=True)
class BoardColumns:
    queued: list[Card]
    running: list[Card]
    needs_you: list[Card]
    done: list[Card]
    failed: list[Card]


@dataclass(frozen=True)
class BoardCounts:
    running: int
    queued: int
    needs_you: int


@dataclass(frozen=True)
class BoardView:
    columns: BoardColumns
    counts: BoardCounts
    generated_at: datetime


# ── the Run detail (SPEC CAP-12, CAP-15) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class Header:
    project: str
    repository: str
    base_branch: str
    #: The initiative or the spec folder this Run was bound to — whichever input it took.
    folder: str
    template: str
    version: int
    harness: str | None
    started_at: datetime | None
    worktree_path: str | None


@dataclass(frozen=True)
class Alert:
    token: str
    reason: str | None
    park_kind: ParkKind | None


@dataclass(frozen=True)
class LatestAttempt:
    n: int
    started_at: datetime | None
    ended_at: datetime | None
    seconds: float | None
    harness: str | None
    model: str | None
    exit_code: int | None
    cost_usd: Decimal | None
    log_tail: list[str]


@dataclass(frozen=True)
class StepRowView:
    seq: int
    path: str
    label: str
    kind: str
    gate: str
    status: str
    token: str
    reason: str | None
    attempts: int
    latest: LatestAttempt | None


@dataclass(frozen=True)
class StoryCell:
    epic_index: int
    story_id: str
    state: str  # "done" | "current" | "future" | "skipped"


@dataclass(frozen=True)
class Cost:
    spent_usd: Decimal
    budget_usd: Decimal
    tokens_in: int
    tokens_out: int
    wall_clock_seconds: float
    active_seconds: int
    provisional: bool
    #: Always `None` in this epic (no tracing UI yet, SPEC CAP-12); typed `str | None`
    #: rather than the narrower `None` so a later story can populate it without widening
    #: this field's type again.
    trace_url: str | None = None


@dataclass(frozen=True)
class Summary:
    progress: Progress | None
    links: list[str]
    skipped: list[str]


@dataclass(frozen=True)
class RunDetailView:
    run: Run
    header: Header
    alert: Alert | None
    steps: list[StepRowView]
    stories: list[StoryCell]
    cost: Cost
    gate_record: list[GateRecord]
    admitted_signals: tuple[SignalKind, ...]
    summary: Summary | None
