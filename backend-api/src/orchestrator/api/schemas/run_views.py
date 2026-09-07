"""The HTTP shape of the Board and the Run detail (4.12, SPEC CAP-12, FR-22, FR-23, FR-28).

One module for both, the way `application/use_cases/run_views.py` is one module for both
pure builders — each `*Out` here is a thin projection of that module's dataclasses, tuples
turned to lists (AD-3: the generated TypeScript says `Array`), `Decimal`/`datetime` turned
to `MoneyStr`/`UtcTimestamp` (`api/schemas/common.py`).

`RunDetailSummaryOut` is `RunSummaryOut` (`api/schemas/runs.py`) plus the extra fields the
Run detail's own `run` field carries — a subclass rather than a fifth restatement of
`RunSummaryOut`'s eleven fields, since it *is* that shape with more on it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.application.use_cases.run_views import (
    Alert,
    BoardView,
    Card,
    Cost,
    Header,
    LatestAttempt,
    Progress,
    RunDetailView,
    StepRowView,
    StoryCell,
    Summary,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.statuses import Actor, GateEvent, ParkKind, RunStatus, SignalKind
from orchestrator.domain.values import Worktree


class WorktreeOut(BaseModel):
    branch: str
    path: str
    created_branch: bool
    pushed: bool

    @classmethod
    def of(cls, worktree: Worktree) -> WorktreeOut:
        return cls(
            branch=worktree.branch,
            path=worktree.path,
            created_branch=worktree.created_branch,
            pushed=worktree.pushed,
        )


class ProgressOut(BaseModel):
    epics_done: int | None
    epics_total: int | None
    stories_done: int
    stories_total: int
    links: int

    @classmethod
    def of(cls, progress: Progress) -> ProgressOut:
        return cls(
            epics_done=progress.epics_done,
            epics_total=progress.epics_total,
            stories_done=progress.stories_done,
            stories_total=progress.stories_total,
            links=progress.links,
        )


# ── the Board (SPEC CAP-12, CAP-14) ───────────────────────────────────────────────────────


class CardOut(BaseModel):
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
    progress: ProgressOut | None
    kind_label: str | None
    age_seconds: float
    needs_you_since: UtcTimestamp | None

    @classmethod
    def of(cls, card: Card) -> CardOut:
        return cls(
            id=card.id,
            token=card.token,
            status=card.status,
            park_kind=card.park_kind,
            branch=card.branch,
            project_name=card.project_name,
            repository_slug=card.repository_slug,
            current_step_label=card.current_step_label,
            harness=card.harness,
            template=card.template,
            version=card.version,
            progress=None if card.progress is None else ProgressOut.of(card.progress),
            kind_label=card.kind_label,
            age_seconds=card.age_seconds,
            needs_you_since=card.needs_you_since,
        )


class BoardColumnsOut(BaseModel):
    queued: list[CardOut]
    running: list[CardOut]
    needs_you: list[CardOut]
    done: list[CardOut]
    failed: list[CardOut]


class BoardCountsOut(BaseModel):
    running: int
    queued: int
    needs_you: int


class BoardOut(BaseModel):
    """`GET /runs?view=board`. Five columns, always present; `counts` sums three of them."""

    columns: BoardColumnsOut
    counts: BoardCountsOut
    generated_at: UtcTimestamp

    @classmethod
    def of(cls, view: BoardView) -> BoardOut:
        return cls(
            columns=BoardColumnsOut(
                queued=[CardOut.of(card) for card in view.columns.queued],
                running=[CardOut.of(card) for card in view.columns.running],
                needs_you=[CardOut.of(card) for card in view.columns.needs_you],
                done=[CardOut.of(card) for card in view.columns.done],
                failed=[CardOut.of(card) for card in view.columns.failed],
            ),
            counts=BoardCountsOut(
                running=view.counts.running,
                queued=view.counts.queued,
                needs_you=view.counts.needs_you,
            ),
            generated_at=view.generated_at,
        )


# ── the Run detail (SPEC CAP-12, CAP-15) ──────────────────────────────────────────────────


class RunDetailSummaryOut(RunSummaryOut):
    """`RunSummaryOut` plus what only the detail's own `run` field carries."""

    inputs: dict[str, Any]
    manual_estimate_h: Decimal | None
    worktree_path: str | None
    worktrees: list[WorktreeOut]
    compare_urls: list[str]
    terminal_session: bool
    accepted_paths: list[str]

    @classmethod
    def of_run(cls, run: Run, *, admitted_signals: tuple[SignalKind, ...]) -> RunDetailSummaryOut:
        """Built on `RunSummaryOut.of` rather than a second, hand-listed field mapping —
        this stays in step with that one automatically if it ever changes. `admitted_signals`
        is recomputed by the caller (`run_detail`, off the parked row's own `kind`) rather
        than `RunSummaryOut.of`'s own `park_row_kind=None` default, so it is overridden here."""
        base = RunSummaryOut.of(run).model_dump()
        base["admitted_signals"] = admitted_signals
        return cls(
            **base,
            inputs=run.inputs,
            manual_estimate_h=run.manual_estimate_h,
            worktree_path=run.worktree_path,
            worktrees=[WorktreeOut.of(worktree) for worktree in run.worktrees],
            compare_urls=list(run.compare_urls),
            terminal_session=run.terminal_session,
            accepted_paths=list(run.accepted_paths),
        )


class HeaderMetaOut(BaseModel):
    project: str
    repository: str
    base_branch: str
    folder: str
    template: str
    version: int
    harness: str | None
    started_at: UtcTimestamp | None
    worktree_path: str | None


class HeaderOut(BaseModel):
    meta: HeaderMetaOut

    @classmethod
    def of(cls, header: Header) -> HeaderOut:
        return cls(
            meta=HeaderMetaOut(
                project=header.project,
                repository=header.repository,
                base_branch=header.base_branch,
                folder=header.folder,
                template=header.template,
                version=header.version,
                harness=header.harness,
                started_at=header.started_at,
                worktree_path=header.worktree_path,
            )
        )


class AlertOut(BaseModel):
    token: str
    reason: str | None
    park_kind: ParkKind | None

    @classmethod
    def of(cls, alert: Alert) -> AlertOut:
        return cls(token=alert.token, reason=alert.reason, park_kind=alert.park_kind)


class LatestAttemptOut(BaseModel):
    n: int
    started_at: UtcTimestamp | None
    ended_at: UtcTimestamp | None
    seconds: float | None
    harness: str | None
    model: str | None
    exit_code: int | None
    cost_usd: MoneyStr | None
    log_tail: list[str]

    @classmethod
    def of(cls, latest: LatestAttempt) -> LatestAttemptOut:
        return cls(
            n=latest.n,
            started_at=latest.started_at,
            ended_at=latest.ended_at,
            seconds=latest.seconds,
            harness=latest.harness,
            model=latest.model,
            exit_code=latest.exit_code,
            cost_usd=latest.cost_usd,
            log_tail=list(latest.log_tail),
        )


class StepRowOut(BaseModel):
    seq: int
    path: str
    label: str
    kind: str
    gate: str
    status: str
    token: str
    reason: str | None
    attempts: int
    latest: LatestAttemptOut | None

    @classmethod
    def of(cls, row: StepRowView) -> StepRowOut:
        return cls(
            seq=row.seq,
            path=row.path,
            label=row.label,
            kind=row.kind,
            gate=row.gate,
            status=row.status,
            token=row.token,
            reason=row.reason,
            attempts=row.attempts,
            latest=None if row.latest is None else LatestAttemptOut.of(row.latest),
        )


class StoryCellOut(BaseModel):
    epic_index: int
    story_id: str
    state: str

    @classmethod
    def of(cls, cell: StoryCell) -> StoryCellOut:
        return cls(epic_index=cell.epic_index, story_id=cell.story_id, state=cell.state)


class CostOut(BaseModel):
    spent_usd: MoneyStr
    budget_usd: MoneyStr
    tokens_in: int
    tokens_out: int
    wall_clock_seconds: float
    active_seconds: int
    provisional: bool
    trace_url: str | None

    @classmethod
    def of(cls, cost: Cost) -> CostOut:
        return cls(
            spent_usd=cost.spent_usd,
            budget_usd=cost.budget_usd,
            tokens_in=cost.tokens_in,
            tokens_out=cost.tokens_out,
            wall_clock_seconds=cost.wall_clock_seconds,
            active_seconds=cost.active_seconds,
            provisional=cost.provisional,
            trace_url=cost.trace_url,
        )


class GateRecordOut(BaseModel):
    id: UUID
    at: UtcTimestamp
    path: str | None
    event: GateEvent
    actor: Actor
    text: str
    attempt_n: int | None

    @classmethod
    def of(cls, record: GateRecord) -> GateRecordOut:
        return cls(
            id=record.id,
            at=record.at,
            path=record.path,
            event=record.event,
            actor=record.actor,
            text=record.text,
            attempt_n=record.attempt_n,
        )


class SummaryOut(BaseModel):
    progress: ProgressOut | None
    links: list[str]
    skipped: list[str]

    @classmethod
    def of(cls, summary: Summary) -> SummaryOut:
        return cls(
            progress=None if summary.progress is None else ProgressOut.of(summary.progress),
            links=list(summary.links),
            skipped=list(summary.skipped),
        )


class RunDetailOut(BaseModel):
    """`GET /runs/{run_id}/detail`. One request, every section the screen shows."""

    run: RunDetailSummaryOut
    header: HeaderOut
    alert: AlertOut | None
    steps: list[StepRowOut]
    stories: list[StoryCellOut]
    cost: CostOut
    gate_record: list[GateRecordOut]
    admitted_signals: tuple[SignalKind, ...]
    summary: SummaryOut | None

    @classmethod
    def of(cls, detail: RunDetailView) -> RunDetailOut:
        return cls(
            run=RunDetailSummaryOut.of_run(detail.run, admitted_signals=detail.admitted_signals),
            header=HeaderOut.of(detail.header),
            alert=None if detail.alert is None else AlertOut.of(detail.alert),
            steps=[StepRowOut.of(row) for row in detail.steps],
            stories=[StoryCellOut.of(cell) for cell in detail.stories],
            cost=CostOut.of(detail.cost),
            gate_record=[GateRecordOut.of(record) for record in detail.gate_record],
            admitted_signals=detail.admitted_signals,
            summary=None if detail.summary is None else SummaryOut.of(detail.summary),
        )
