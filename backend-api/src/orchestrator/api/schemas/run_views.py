"""The HTTP shape of the Board and the Run detail (4.12, SPEC CAP-12, FR-22, FR-23, FR-28).

One module for both, the way `application/use_cases/run_views.py` is one module for both
pure builders — each `*Out` here is a thin projection of that module's dataclasses, tuples
turned to lists (AD-3: the generated TypeScript says `Array`), `Decimal`/`datetime` turned
to `MoneyStr`/`UtcTimestamp` (`api/schemas/common.py`).

`RunDetailSummaryOut` is `RunSummaryOut` (`api/schemas/runs.py`) plus the extra fields the
Run detail's own `run` field carries — a subclass rather than a fifth restatement of
`RunSummaryOut`'s eleven fields, since it *is* that shape with more on it.

The Board's own shapes (`ProgressOut` through `BoardOut`) moved to `api/schemas/board_view.py`
on line count alone (5.10) — imported back below so every existing import of `BoardOut`/
`CardOut` off this module keeps resolving.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from orchestrator.api.schemas.board_view import (
    BoardColumnsOut,
    BoardCountsOut,
    BoardOut,
    CardOut,
    ProgressOut,
)
from orchestrator.api.schemas.common import MoneyStr, UtcTimestamp
from orchestrator.api.schemas.run_alert import AlertOut, AttributionOut, CheckpointStoryOut
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.application.use_cases.run_views import (
    Cost,
    Header,
    LatestAttempt,
    RunDetailView,
    StepRowView,
    StoryCell,
    Summary,
    Terminal,
)
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.statuses import Actor, GateEvent, SignalKind
from orchestrator.domain.values import Worktree

__all__ = [
    "AlertOut",
    "AttributionOut",
    "BoardColumnsOut",
    "BoardCountsOut",
    "BoardOut",
    "CardOut",
    "CheckpointStoryOut",
    "ProgressOut",
    "RunDetailOut",
]


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


def _drop_default(schema: dict[str, Any]) -> None:
    """Strip the JSON-schema `default` a defaulted field carries, so `openapi-typescript`
    (`defaultNonNullable`) still emits it as optional — an existing web-client test fixture
    predates `cost_usd` below and must keep compiling without it."""
    schema.pop("default", None)


# ── the Run detail (SPEC CAP-12, CAP-15) ──────────────────────────────────────────────────


class TerminalOut(BaseModel):
    """The resume command block (6.7, FR-21, UX-DR5).

    **`command` never carries a secret value** (AD-5): it is built from this attempt's
    identifiers, and every credential in it is a shell reference the container resolves —
    `application/use_cases/terminal.py` states the mechanism, and
    `tests/unit/test_terminal_command.py` asserts the absence.
    """

    command: str
    session_lifetime_ends_at: UtcTimestamp | None
    in_progress: bool

    @classmethod
    def of(cls, terminal: Terminal) -> TerminalOut:
        return cls(
            command=terminal.command,
            session_lifetime_ends_at=terminal.session_lifetime_ends_at,
            in_progress=terminal.in_progress,
        )


class RunDetailSummaryOut(RunSummaryOut):
    """`RunSummaryOut` plus what only the detail's own `run` field carries."""

    inputs: dict[str, Any]
    manual_estimate_h: Decimal | None
    worktree_path: str | None
    worktrees: list[WorktreeOut]
    compare_urls: list[str]
    terminal_session: bool
    accepted_paths: list[str]
    #: FR-21's resume command, beside the flag that says whether a session is already open
    #: (6.7). It belongs to the Run rather than to the screen's own sections: `in_progress`
    #: *is* `terminal_session` one line above, and a block whose whole subject is a field of
    #: `run` reads truer here than as a tenth top-level key. `null` for every stop the
    #: escape hatch does not apply to; `_drop_default`-guarded like `skipped_epics`, so the
    #: web-client fixtures that predate it keep compiling without it (AD-3).
    terminal: TerminalOut | None = Field(default=None, json_schema_extra=_drop_default)
    #: When the detail was last opened via `?opened=1` (8-3). `null` on first ever open or
    #: when the Run was never fetched with `?opened=1`. `_drop_default`-guarded so every
    #: existing web-client fixture that predates this field keeps compiling without it.
    last_opened_at: datetime | None = Field(default=None, json_schema_extra=_drop_default)

    @classmethod
    def of_run(
        cls,
        run: Run,
        *,
        admitted_signals: tuple[SignalKind, ...],
        terminal: Terminal | None = None,
    ) -> RunDetailSummaryOut:
        """Built on `RunSummaryOut.of` rather than a second, hand-listed field mapping —
        this stays in step with that one automatically if it ever changes. `admitted_signals`
        is recomputed by the caller (`run_detail`, off the parked row's own `kind`) rather
        than `RunSummaryOut.of`'s own `park_row_kind=None` default, so it is overridden here.
        `terminal` is the caller's for the same reason: it is built from the parked row's own
        attempt and the harness registry, neither of which a `Run` carries."""
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
            terminal=None if terminal is None else TerminalOut.of(terminal),
            last_opened_at=run.last_opened_at,
        )


class HeaderMetaOut(BaseModel):
    project: str
    repository: str
    base_branch: str
    folder: str
    template: str
    version: int
    harness: str | None
    #: The model the dispatch used — EXPERIENCE-v1.md delta 26 (2026-09-15).
    model: str | None = None
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
                model=header.model,
                started_at=header.started_at,
                worktree_path=header.worktree_path,
            )
        )


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
    #: See `StepRowOut.cost_usd`'s own comment; predates this field (5.10).
    cost_provisional: bool = Field(default=False, json_schema_extra=_drop_default)

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
            cost_provisional=latest.cost_provisional,
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
    #: `.of()` always sets the real value; see `_drop_default` for why schema-optional.
    cost_usd: MoneyStr = Field(default=Decimal("0"), json_schema_extra=_drop_default)

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
            cost_usd=row.cost_usd,
        )


class StoryCellOut(BaseModel):
    epic_index: int
    story_id: str
    state: str
    #: See `StepRowOut.cost_usd`'s own comment.
    cost_usd: MoneyStr = Field(default=Decimal("0"), json_schema_extra=_drop_default)

    @classmethod
    def of(cls, cell: StoryCell) -> StoryCellOut:
        return cls(
            epic_index=cell.epic_index,
            story_id=cell.story_id,
            state=cell.state,
            cost_usd=cell.cost_usd,
        )


class CostOut(BaseModel):
    spent_usd: MoneyStr
    budget_usd: MoneyStr | None
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
    #: The epic numbers `skip_epic` gave up the push on (6.5). `_drop_default`-guarded like
    #: `cost_provisional`/`row_kind` above: an existing web-client test fixture predates this
    #: field and must keep compiling without it.
    skipped_epics: list[int] = Field(default_factory=list, json_schema_extra=_drop_default)

    @classmethod
    def of(cls, summary: Summary) -> SummaryOut:
        return cls(
            progress=None if summary.progress is None else ProgressOut.of(summary.progress),
            links=list(summary.links),
            skipped=list(summary.skipped),
            skipped_epics=list(summary.skipped_epics),
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
            run=RunDetailSummaryOut.of_run(
                detail.run,
                admitted_signals=detail.admitted_signals,
                terminal=detail.terminal,
            ),
            header=HeaderOut.of(detail.header),
            alert=None if detail.alert is None else AlertOut.of(detail.alert),
            steps=[StepRowOut.of(row) for row in detail.steps],
            stories=[StoryCellOut.of(cell) for cell in detail.stories],
            cost=CostOut.of(detail.cost),
            gate_record=[GateRecordOut.of(record) for record in detail.gate_record],
            admitted_signals=detail.admitted_signals,
            summary=None if detail.summary is None else SummaryOut.of(detail.summary),
        )
