"""The Board's and the Run detail's own dataclasses (SPEC CAP-12, FR-22, FR-23, FR-28).

Split out of `application/use_cases/run_views.py` on line count alone (`backend-api/
AGENTS.md`'s 400-line module limit) — the pure builders (`board_view`, `run_detail`) and
every private helper stay there; only the shapes they build live here, the same split
`application/graph.py`/`graph_schema.py` uses for the same reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.use_cases.terminal import Terminal, TerminalPorts
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
from orchestrator.domain.ports.tracer import Tracer
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
    #: `None` degrades to `cost.trace_url = None` (AD-11) — every frozen `RunViewPorts(...)`
    #: construction predating this story (`test_run_views.py`'s own `harness` fixture)
    #: keeps working unchanged. Production wiring always sets one.
    tracer: Tracer | None = None
    #: `None` degrades to `terminal = None` (FR-21, 6.7), for the same reason and with the
    #: same precedent: a read that was not wired for the resume command simply publishes no
    #: `terminal` block, and every `RunViewPorts(...)` written before this story compiles.
    terminal: TerminalPorts | None = None


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
class Attribution:
    """Who a `blocked` park's Question is attributed to (SPEC CAP-10): the parked row's own
    latest Attempt, whose `harness`/`model`/`ended_at` are already settled by the time a
    Story can block (`mark_finished` before `apply_step_result` ever routes one) — `None`
    only for a park kind whose row never ran an Attempt."""

    harness: str | None
    model: str | None
    ended_at: datetime | None


@dataclass(frozen=True)
class CheckpointStory:
    """The done-checkpoint's own summary line (story 6-2, SPEC CAP-2): `story {id} · {title}
    · {attempts} attempts · ${cost} · verify {done|skipped}`. `None` on `Alert` for every
    stop but a `checkpoint` park on a row that is not itself `agent` — a spec checkpoint
    shows the planned file inline instead (`run_files.py`), not this summary."""

    story_id: str
    title: str
    attempts: int
    cost_usd: Decimal
    verify: str


@dataclass(frozen=True)
class Alert:
    token: str
    reason: str | None
    park_kind: ParkKind | None
    #: `None` predates this story; every `blocked` park now carries one (5.10).
    attribution: Attribution | None = None
    #: The parked row's own `kind` (story 6-2): a `checkpoint` park's `StopBody` case is
    #: `agent` (spec checkpoint, the planned file inline) or anything else (done checkpoint,
    #: `checkpoint_story` below). `None` predates this story.
    row_kind: str | None = None
    #: Set only for a done checkpoint (`row_kind` not `agent`, `park_kind == "checkpoint"`).
    checkpoint_story: CheckpointStory | None = None
    #: The payload of the gate record that parked this Run (6.6) — `{}` for every stop that
    #: kept none. AD-17's hit list is what travels on one today, and the protected-path body
    #: renders each file's added/deleted/modified mark and diff link from these entries.
    payload: dict[str, Any] = field(default_factory=dict)


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
    #: True while `cost_usd` is the harness's own estimate (5.10, off `Attempt.cost_provisional`).
    cost_provisional: bool = False


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
    #: This row's own attempts, summed (5.3). Defaulted: predates this story.
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class StoryCell:
    epic_index: int
    story_id: str
    state: str  # "done" | "current" | "future" | "skipped"
    #: This frame's own rows' attempts, summed (5.3). Defaulted: predates this story.
    cost_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class Cost:
    spent_usd: Decimal
    budget_usd: Decimal
    tokens_in: int
    tokens_out: int
    wall_clock_seconds: float
    active_seconds: int
    provisional: bool
    #: The Langfuse UI link for this Run's trace (AD-11), or `None` when `run.trace_id` was
    #: never set (no tracer wired at Run creation) or no `Tracer` is wired on this read.
    trace_url: str | None = None


@dataclass(frozen=True)
class Summary:
    progress: Progress | None
    links: list[str]
    skipped: list[str]
    #: The 1-based epic numbers `skip_epic` gave up the push on (6.5, FR-20) — defaulted so
    #: `tests/unit/test_run_view_schemas.py`'s existing `Summary(...)` construction, which
    #: predates this field, keeps compiling unedited.
    skipped_epics: list[int] = field(default_factory=list)


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
    #: The paste-able resume command and its session state (6.7, FR-21), or `None` for every
    #: stop the terminal escape hatch does not apply to. Defaulted, so `run_detail`'s own
    #: existing constructions and the tests that build a `RunDetailView` by hand keep
    #: compiling — `use_cases/terminal.py`'s docstring lists the five `None` cases.
    terminal: Terminal | None = None
