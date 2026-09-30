"""The Board, the Run detail, and their shared pieces (SPEC CAP-12, FR-22, FR-23, FR-28).

Three read models, one module, because the Board card and the Run detail's `run` field
answer overlapping questions from the same rows — the UI status token, the current step's
label, the epic/story progress — and a second module would either duplicate that or import
across use cases for a handful of lines, which this codebase's own convention (`application/
use_cases/queue.py` vs `project_runs.py`) already resolves by small local duplication
instead. The run *graph* is not here: `build_run_graph` lives beside `build_template_graph`
in `application/graph.py` (Epic 3's hand-off), and this module leans on that module's
`STEP_TOKENS` table so the two never state the mapping twice.

Two seams have since been cut out of it for length rather than for design — `run_views_alert.py`
(6.2) and `run_views_summary.py` (6.4), each 400 lines' worth of pressure on a module that had
none to spare. Both are imported straight back under the private names this module already
used, so the paragraph above still describes how the three read models are assembled.

`run_detail` and the run graph route share `RunViewPorts`, a fresh, fully-required ports bundle
behind a brand new dependency (`api/providers.py::run_view_ports`) — both are new routes with no
existing caller to keep working. `board_view` cannot: it answers `GET /runs?view=board`, the
*same* route and the *same* `run_read_ports` dependency `GET /runs` (no `view`) already uses, and
`tests/unit/test_run_router.py` overrides that dependency with a `RunReadPorts(runs=self.runs)`
built years before this story — adding a second, required dependency to that route's handler would
resolve it unconditionally on every call and crash that existing test's plain list. So
`board_view` reads through `RunReadPorts` instead (`application/use_cases/create_run.py`, extended
here with the optional `projects`/`repositories`/`gate_records` fields it needs, following the
same "`None` where a caller does not wire it" precedent `steps` already set on that dataclass),
and takes `now` as a plain argument rather than a `Clock` port — the router already has one free
to call (`SystemClock` from `infrastructure/`, which `api/` may import) and a Board read gains
nothing from making that a fourth optional port to thread through.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from orchestrator.application.graph import STEP_TOKENS
from orchestrator.application.rules.signals import row_at, run_admitted_signals
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_graph import run_graph_for
from orchestrator.application.use_cases.run_view_types import (
    Alert,
    Attribution,
    BoardColumns,
    BoardCounts,
    BoardView,
    Card,
    CheckpointStory,
    Cost,
    Header,
    LatestAttempt,
    Progress,
    RunDetailView,
    RunViewPorts,
    StepRowView,
    StoryCell,
    Summary,
)
from orchestrator.application.use_cases.run_views_alert import build_alert, run_token
from orchestrator.application.use_cases.run_views_summary import (
    bracket_index,
    progress,
    story_cells,
    summary,
)
from orchestrator.application.use_cases.terminal import Terminal, resume_command
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.tracer import Tracer

__all__ = [
    "Alert",
    "Attribution",
    "BoardColumns",
    "BoardCounts",
    "BoardView",
    "Card",
    "CheckpointStory",
    "Cost",
    "Header",
    "LatestAttempt",
    "Progress",
    "RunDetailView",
    "RunViewPorts",
    "StepRowView",
    "StoryCell",
    "Summary",
    "Terminal",
    "board_view",
    "run_detail",
    "run_graph_for",
]

#: The kind-to-`kind_label` a Card shows (SPEC CAP-12); `readiness` is unshipped but free to name.
_KIND_LABELS: dict[str, str] = {"repo-init": "repo-init", "readiness": "readiness"}

#: `run_token`/`build_alert` live in `run_views_alert.py` now, and the epic/story arithmetic
#: — progress, the Story cells, the summary — in `run_views_summary.py` (line count alone,
#: 6.2's own seam; see those modules' docstrings). The private names every call site here
#: already used stay bound to them, so nothing else in this module changed.
_run_token = run_token
_bracket_index = bracket_index
_progress = progress
_story_cells = story_cells
_summary = summary


# ── the Board (SPEC CAP-12, CAP-14) ───────────────────────────────────────────────────────


def board_view(ports: RunReadPorts, *, project_id: UUID | None, now: datetime) -> BoardView:
    """Every Run, one card each, in its column — `cancelled` files under `failed` (CAP-14)."""
    cards = [_card(ports, run, now=now) for run in ports.runs.list(project_id=project_id)]
    columns = BoardColumns(
        queued=[card for card in cards if card.status == "queued"],
        running=[card for card in cards if card.status == "running"],
        needs_you=[card for card in cards if card.status == "needs_you"],
        done=[card for card in cards if card.status == "done"],
        failed=[card for card in cards if card.status in ("failed", "cancelled")],
    )
    counts = BoardCounts(
        running=len(columns.running),
        queued=len(columns.queued),
        needs_you=len(columns.needs_you),
    )
    return BoardView(columns=columns, counts=counts, generated_at=now)


def _card(ports: RunReadPorts, run: Run, *, now: datetime) -> Card:
    steps = ports.steps.list_for_run(run.id) if ports.steps is not None else []
    project = ports.projects.get(run.project_id) if ports.projects is not None else None
    repository = (
        ports.repositories.get(run.repository_id) if ports.repositories is not None else None
    )
    return Card(
        id=run.id,
        token=_run_token(run),
        status=run.status,
        park_kind=run.park_kind,
        branch=str(run.inputs.get("base_branch", "")),
        project_name=project.name if project is not None else "",
        repository_slug=repository.slug if repository is not None else "",
        current_step_label=_board_current_step_label(run, steps),
        harness=run.inputs.get("harness"),
        template=run.template_name,
        version=run.template_version,
        progress=_progress(run, steps),
        kind_label=_KIND_LABELS.get(run.template_name),
        age_seconds=(now - run.created_at).total_seconds(),
        needs_you_since=_needs_you_since(ports, run) if run.status == "needs_you" else None,
    )


def _board_current_step_label(run: Run, steps: Sequence[StepRun]) -> str:
    """The running row's label, else the park row's, else the last `done` row's (CAP-12)."""
    running = next((row for row in steps if row.status == "running"), None)
    if running is not None:
        return running.label
    parked = row_at(steps, run.park_path)
    if parked is not None:
        return parked.label
    done = [row for row in steps if row.status == "done"]
    return done[-1].label if done else ""


def _needs_you_since(ports: RunReadPorts, run: Run) -> datetime | None:
    """The `.at` of the most recent gate record matching `run.park_kind` — the only durable
    record of when a Run parked (`Run` itself carries no such timestamp)."""
    if ports.gate_records is None:
        return None
    records = ports.gate_records.list_for_run(run.id)
    matching = [record for record in records if record.event == run.park_kind]
    return matching[-1].at if matching else None


# ── the Run detail (SPEC CAP-12, CAP-15) ──────────────────────────────────────────────────


def run_detail(ports: RunViewPorts, run_id: UUID) -> RunDetailView:
    """The one read `GET /runs/{id}/detail` needs — everything the Run detail screen shows."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    rows = ports.steps.list_for_run(run.id)
    attempts_by_row = {row.id: ports.attempts.list_for_row(row.id) for row in rows}
    project = ports.projects.get(run.project_id)
    repository = ports.repositories.get(run.repository_id)
    park_row = row_at(rows, run.park_path)
    admitted = run_admitted_signals(
        run,
        park_row.kind if park_row is not None else None,
        park_row_status=park_row.status if park_row is not None else None,
    )
    park_attempts = attempts_by_row.get(park_row.id, ()) if park_row is not None else ()
    # Read once and shared: the detail publishes the whole gate record, and `_alert` needs
    # the park's own entry off the same list (6.6) rather than a second query for it.
    records = ports.gate_records.list_for_run(run.id)
    reply_available, resume_unavailable_reason = _reply_status(ports, run)
    return RunDetailView(
        run=run,
        header=_header(run, project, repository),
        alert=_alert(run, _latest_of(park_attempts), rows, park_row, attempts_by_row, records),
        steps=[_step_row(ports, row, attempts_by_row[row.id]) for row in rows],
        stories=_story_cells(run, rows, attempts_by_row),
        cost=_cost(run, attempts_by_row, now=ports.clock.now(), tracer=ports.tracer),
        gate_record=records,
        admitted_signals=admitted,
        summary=_summary(run, rows),
        terminal=_terminal(ports, run, park_row, _latest_of(park_attempts), project),
        reply_available=reply_available,
        resume_unavailable_reason=resume_unavailable_reason,
    )


def _terminal(
    ports: RunViewPorts,
    run: Run,
    park_row: StepRun | None,
    attempt: Attempt | None,
    project: Project | None,
) -> Terminal | None:
    """FR-21's resume command, or `None` when this read was not wired for one.

    The unwired case is the `tracer` precedent one layer on: a `RunViewPorts` built without
    `terminal` publishes no `terminal` block rather than failing, which is what keeps every
    frozen construction of that dataclass compiling. `use_cases/terminal.py` owns the five
    reasons a *wired* read still answers `None`.
    """
    if ports.terminal is None:
        return None
    return resume_command(
        ports.terminal,
        run,
        park_row,
        attempt,
        project_slug=project.slug if project is not None else "",
    )


def _reply_status(ports: RunViewPorts, run: Run) -> tuple[bool, str | None]:
    """Reply availability and the reason when unavailable (story 4, 2026-09-25).

    Returns `(True, None)` when the latest attempt has a session_id and the harness supports
    resume; `(False, "no_session")` when no attempt exists or no session_id was recorded;
    `(False, "no_capability")` when a session_id was recorded but the harness cannot resume;
    `(False, None)` when `harness_is_resumable` is not wired (safe-unwired case, same
    precedent as `terminal`).
    """
    if ports.harness_is_resumable is None:
        return False, None
    a = ports.attempts.latest_for_run(run.id)
    if a is None or a.session_id is None:
        return False, "no_session"
    harness = a.harness or ""
    if not ports.harness_is_resumable(harness):
        return False, "no_capability"
    return True, None


def _header(run: Run, project: Project | None, repository: Repository | None) -> Header:
    return Header(
        project=project.name if project is not None else "",
        repository=repository.slug if repository is not None else "",
        base_branch=str(run.inputs.get("base_branch", "")),
        folder=str(run.inputs.get("spec_folder") or run.inputs.get("initiative_folder") or ""),
        template=run.template_name,
        version=run.template_version,
        harness=run.inputs.get("harness"),
        model=run.inputs.get("model"),
        started_at=run.started_at,
        worktree_path=run.worktree_path,
    )


def _alert(  # noqa: PLR0913, PLR0917 — the positional adapter 6.2's split left
    run: Run,
    attempt: Attempt | None,
    rows: Sequence[StepRun],
    park_row: StepRun | None,
    attempts_by_row: Mapping[UUID, Sequence[Attempt]],
    records: Sequence[GateRecord] = (),
) -> Alert | None:
    row_kind = park_row.kind if park_row is not None else None
    return build_alert(
        run,
        attempt,
        row_kind=row_kind,
        rows=rows,
        park_row=park_row,
        attempts_by_row=attempts_by_row,
        records=records,
    )


def _latest_of(attempts: Sequence[Attempt]) -> Attempt | None:
    return max(attempts, key=lambda attempt: attempt.n, default=None)


def _step_row(ports: RunViewPorts, row: StepRun, attempts: Sequence[Attempt]) -> StepRowView:
    latest = _latest_of(attempts)
    cost_usd = sum((attempt.cost_usd or Decimal("0") for attempt in attempts), Decimal("0"))
    retry_prompt = (
        row.with_resolved.get("retry", {}).get("prompt")
        if isinstance(row.with_resolved.get("retry"), dict)
        else None
    )
    return StepRowView(
        seq=row.seq,
        path=row.path,
        label=row.label,
        kind=row.kind,
        gate=row.gate,
        status=row.status,
        token=STEP_TOKENS[row.status],
        reason=row.reason,
        attempts=len(attempts),
        latest=_latest_attempt(ports, latest) if latest is not None else None,
        cost_usd=cost_usd,
        retry_prompt=retry_prompt if isinstance(retry_prompt, str) else None,
    )


def _latest_attempt(ports: RunViewPorts, attempt: Attempt) -> LatestAttempt:
    seconds = None
    if attempt.started_at is not None and attempt.ended_at is not None:
        seconds = (attempt.ended_at - attempt.started_at).total_seconds()
    return LatestAttempt(
        n=attempt.n,
        started_at=attempt.started_at,
        ended_at=attempt.ended_at,
        seconds=seconds,
        harness=attempt.harness,
        model=attempt.model,
        exit_code=attempt.exit_code,
        cost_usd=attempt.cost_usd,
        log_tail=ports.logs.tail(attempt.log_path, 40),
        cost_provisional=attempt.cost_provisional,
    )


def _cost(
    run: Run,
    attempts_by_row: Mapping[UUID, Sequence[Attempt]],
    *,
    now: datetime,
    tracer: Tracer | None,
) -> Cost:
    every_attempt = [attempt for attempts in attempts_by_row.values() for attempt in attempts]
    wall_clock = 0.0
    if run.started_at is not None:
        end = run.ended_at or _latest_seen(every_attempt) or now
        wall_clock = max((end - run.started_at).total_seconds(), 0.0)
    return Cost(
        spent_usd=run.spend_usd,
        budget_usd=run.budget_usd,
        tokens_in=sum(attempt.tokens_in or 0 for attempt in every_attempt),
        tokens_out=sum(attempt.tokens_out or 0 for attempt in every_attempt),
        wall_clock_seconds=wall_clock,
        active_seconds=run.active_seconds,
        provisional=any(attempt.cost_provisional for attempt in every_attempt),
        trace_url=tracer.trace_url(run.trace_id) if (tracer is not None and run.trace_id) else None,
    )


def _latest_seen(attempts: Sequence[Attempt]) -> datetime | None:
    """The most recent `ended_at` among finished attempts — a running Run's wall clock end
    while it has no `run.ended_at` yet."""
    ended = [attempt.ended_at for attempt in attempts if attempt.ended_at is not None]
    return max(ended) if ended else None
