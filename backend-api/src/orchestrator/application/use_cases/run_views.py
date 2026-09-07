"""The Board, the Run detail, and their shared pieces (SPEC CAP-12, FR-22, FR-23, FR-28).

Three read models, one module, because the Board card and the Run detail's `run` field
answer overlapping questions from the same rows — the UI status token, the current step's
label, the epic/story progress — and a second module would either duplicate that or import
across use cases for a handful of lines, which this codebase's own convention (`application/
use_cases/queue.py` vs `project_runs.py`) already resolves by small local duplication
instead. The run *graph* is not here: `build_run_graph` lives beside `build_template_graph`
in `application/graph.py` (Epic 3's hand-off), and this module leans on that module's
`STEP_TOKENS` table so the two never state the mapping twice.

`run_detail` and the run graph route share `RunViewPorts`, a fresh, fully-required ports
bundle behind a brand new dependency (`api/providers.py::run_view_ports`) — both are new
routes with no existing caller to keep working. `board_view` cannot: it answers
`GET /runs?view=board`, the *same* route and the *same* `run_read_ports` dependency
`GET /runs` (no `view`) already uses, and `tests/unit/test_run_router.py` overrides that
dependency with a `RunReadPorts(runs=self.runs)` built years before this story — adding a
second, required dependency to that route's handler would resolve it unconditionally on
every call and crash that existing test's plain list. So `board_view` reads through
`RunReadPorts` instead (`application/use_cases/create_run.py`, extended here with the
optional `projects`/`repositories`/`gate_records` fields it needs, following the same
"`None` where a caller does not wire it" precedent `steps` already set on that dataclass),
and takes `now` as a plain argument rather than a `Clock` port — the router already has one
free to call (`SystemClock` from `infrastructure/`, which `api/` may import) and a Board
read gains nothing from making that a fourth optional port to thread through.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import UUID

from orchestrator.application.graph import STEP_TOKENS, Graph, build_run_graph
from orchestrator.application.rules.frames import epic_frame, story_frame
from orchestrator.application.rules.signals import row_at, run_admitted_signals
from orchestrator.application.steps import COMMIT_KIND, PUSH_KIND
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.run_view_types import (
    Alert,
    BoardColumns,
    BoardCounts,
    BoardView,
    Card,
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
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.domain.statuses import RunStatus

__all__ = [
    "Alert",
    "BoardColumns",
    "BoardCounts",
    "BoardView",
    "Card",
    "Cost",
    "Header",
    "LatestAttempt",
    "Progress",
    "RunDetailView",
    "RunViewPorts",
    "StepRowView",
    "StoryCell",
    "Summary",
    "board_view",
    "run_detail",
    "run_graph_for",
]

#: The two Templates whose Runs carry epic/story progress (SPEC CAP-12). Every other
#: Template — `repo-init` today — has no `epics[i]`/`stories[j]` frame in any of its rows.
_PROGRESS_TEMPLATES = ("epic", "initiative")

#: The kind-to-`kind_label` a Card shows, for the Templates that have one (SPEC CAP-12).
#: `readiness` is not shipped yet; naming it here costs nothing and needs no later change.
_KIND_LABELS: dict[str, str] = {"repo-init": "repo-init", "readiness": "readiness"}

#: The statuses that finish a frame's own row, one way or the other (AD-9's own pair).
_SETTLED: tuple[str, ...] = ("done", "skipped")

_BRACKET_INDEX = re.compile(r"\[(\d+)\]$")

#: The Run's own UI token (Consistency Conventions — Status tokens): `BLK`/`CHK` while
#: parked, off `park_kind`, the fixed table otherwise. Duplicated from `application/
#: use_cases/project_runs.py::_token` and `application/graph.py::_run_token` — each reader's
#: own small pure function, the established precedent for a handful of lines (see
#: `project_runs.py`'s own docstring on `_current_step_label`).
_RUN_TOKENS: dict[RunStatus, str] = {
    "queued": "QUE",
    "running": "RUN",
    "done": "DON",
    "failed": "ERR",
    "cancelled": "CAN",
}


def _run_token(run: Run) -> str:
    if run.status == "needs_you":
        return "CHK" if run.park_kind == "checkpoint" else "BLK"
    return _RUN_TOKENS[run.status]


def _progress(run: Run, rows: Sequence[StepRun]) -> Progress | None:
    """`None` for a Run whose Template has no epic/story frame at all (e.g. `repo-init`)."""
    if run.template_name not in _PROGRESS_TEMPLATES:
        return None
    story_commits = [row for row in rows if row.kind == COMMIT_KIND]
    stories_total = len(story_commits)
    stories_done = sum(1 for row in story_commits if row.status in _SETTLED)
    epics_total: int | None = None
    epics_done: int | None = None
    if run.template_name == "initiative":
        epic_pushes = [row for row in rows if row.kind == PUSH_KIND]
        epics_total = len(epic_pushes)
        epics_done = sum(1 for row in epic_pushes if row.status in _SETTLED)
    return Progress(
        epics_done=epics_done,
        epics_total=epics_total,
        stories_done=stories_done,
        stories_total=stories_total,
        links=len(run.compare_urls),
    )


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
    admitted = run_admitted_signals(run, park_row.kind if park_row is not None else None)
    return RunDetailView(
        run=run,
        header=_header(run, project, repository),
        alert=_alert(run),
        steps=[_step_row(ports, row, attempts_by_row[row.id]) for row in rows],
        stories=_story_cells(run, rows),
        cost=_cost(run, attempts_by_row, now=ports.clock.now(), tracer=ports.tracer),
        gate_record=ports.gate_records.list_for_run(run.id),
        admitted_signals=admitted,
        summary=_summary(run, rows),
    )


def _header(run: Run, project: Project | None, repository: Repository | None) -> Header:
    return Header(
        project=project.name if project is not None else "",
        repository=repository.slug if repository is not None else "",
        base_branch=str(run.inputs.get("base_branch", "")),
        folder=str(run.inputs.get("spec_folder") or run.inputs.get("initiative_folder") or ""),
        template=run.template_name,
        version=run.template_version,
        harness=run.inputs.get("harness"),
        started_at=run.started_at,
        worktree_path=run.worktree_path,
    )


def _alert(run: Run) -> Alert | None:
    if run.status != "needs_you":
        return None
    return Alert(token=_run_token(run), reason=run.park_reason, park_kind=run.park_kind)


def _step_row(ports: RunViewPorts, row: StepRun, attempts: Sequence[Attempt]) -> StepRowView:
    latest = max(attempts, key=lambda attempt: attempt.n, default=None)
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
    )


def _story_cells(run: Run, rows: Sequence[StepRun]) -> list[StoryCell]:
    """One cell per story frame, in plan order — state off the frame's own commit-guard row."""
    commit_rows = sorted((row for row in rows if row.kind == COMMIT_KIND), key=lambda row: row.seq)
    cells = []
    for commit_row in commit_rows:
        frame = story_frame(commit_row.path)
        if frame is None:
            continue
        cells.append(_story_cell(run, rows, frame, commit_row))
    return cells


def _story_cell(run: Run, rows: Sequence[StepRun], frame: str, commit_row: StepRun) -> StoryCell:
    epic = epic_frame(frame)
    epic_index = _bracket_index(epic) if epic is not None else 0
    if commit_row.status == "skipped":
        state = "skipped"
    elif commit_row.status == "done":
        state = "done"
    elif _frame_is_current(run, rows, frame):
        state = "current"
    else:
        state = "future"
    return StoryCell(epic_index=epic_index, story_id=commit_row.story_id or "", state=state)


def _frame_is_current(run: Run, rows: Sequence[StepRun], frame: str) -> bool:
    """The same "current" concept `application/graph.py::_is_current` states per row, here
    over a whole frame: any member is running, or is the parked row (guarded on
    `park_path is not None` for the same reason that function is, even though `row.path`
    being a non-empty `str` already makes `row.path == None` impossible)."""
    return any(
        row.status == "running" or (run.park_path is not None and row.path == run.park_path)
        for row in rows
        if row.path == frame or row.path.startswith(f"{frame}.")
    )


def _bracket_index(prefix: str) -> int:
    match = _BRACKET_INDEX.search(prefix)
    return int(match.group(1)) if match else 0


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


def _summary(run: Run, rows: Sequence[StepRun]) -> Summary | None:
    if run.status != "done":
        return None
    skipped = [
        row.story_id
        for row in rows
        if row.kind == COMMIT_KIND and row.status == "skipped" and row.story_id is not None
    ]
    return Summary(progress=_progress(run, rows), links=list(run.compare_urls), skipped=skipped)


# ── the run graph route's one fetch (SPEC CAP-12, AD-15) ─────────────────────────────────


def run_graph_for(ports: RunViewPorts, run_id: UUID) -> Graph:
    """The one read `GET /runs/{id}/graph` needs: the Run and its rows, then `build_run_graph`
    (`application/graph.py`). Raising `NotFound` here, not in the router, matches `run_detail`
    (above) and `create_run.py::get_run` — the router stays a thin parse-call-map, per
    `backend-api/AGENTS.md`'s "Routers are thin" rule."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    rows = ports.steps.list_for_run(run_id)
    return build_run_graph(rows, run)
