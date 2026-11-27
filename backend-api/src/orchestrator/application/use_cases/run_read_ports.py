"""What the Run read routes read through: `RunReadPorts` and the helpers over it."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

from orchestrator.application.rules.signals import row_at
from orchestrator.application.steps.context import WorkspaceFactory
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ports.initiatives import InitiativeRepository
from orchestrator.domain.ports.repositories import (
    AttemptRepository,
    GateRecordRepository,
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.templates import TemplateVersionRepository


@dataclass(frozen=True)
class RunReadPorts:
    """What `GET /runs`, `GET /runs/{id}` and `GET /runs?view=board` (4.12) read through —
    nothing any of them writes."""

    runs: RunRepository
    #: `None` for a caller that only ever reads a Run — `test_run_router.py` (4.4)
    #: constructs `RunReadPorts(runs=...)` alone. Set, a reader can also look up the parked
    #: row's own `kind` for `RunSummaryOut.admitted_signals` (4.9), and the Board (4.12)
    #: reads a Run's rows for its progress and current-step label.
    steps: StepRunRepository | None = None
    #: `None` for the same reason `steps` can be: the Board (4.12) names and slugs each
    #: card with these, gracefully blank when unwired, the way `application/use_cases/
    #: project_runs.py::embedded_runs` degrades rather than fails a read `runs`/`steps`
    #: alone can already answer.
    projects: ProjectRepository | None = None
    repositories: RepositoryRepository | None = None
    #: `None` likewise; the Board (4.12) reads this for `needs_you_since` alone.
    gate_records: GateRecordRepository | None = None
    #: `None` for the board's attention, initiative tag and template type: each reads its own port.
    attempts: AttemptRepository | None = None
    initiatives: InitiativeRepository | None = None
    templates: TemplateVersionRepository | None = None
    workspace: WorkspaceFactory | None = None


def get_run(ports: RunReadPorts, run_id: UUID) -> Run:
    """One stored Run, or `NotFound` (404) — the minimal read model 4.12 replaces."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run {run_id}")
    return run


def run_rows(ports: RunReadPorts, run: Run) -> list[StepRun]:
    """Every row of this Run, or `[]` when no `StepRunRepository` was wired (4.4's own read
    ports). A single-Run read model wants them for the one question the Run row alone cannot
    answer: whether the whole plan is one epic, which is what admits *Skip epic* at a stop
    with no `epics[n]` frame under it (`rules/frames.py::run_is_one_epic`, Operator decision
    2026-09-30: no template name hardcoded in product code)."""
    return [] if ports.steps is None else list(ports.steps.list_for_run(run.id))


def park_row_in(run: Run, rows: Sequence[StepRun]) -> StepRun | None:
    """The row this Run is parked on, out of rows already read — the pure half of
    `park_row_of`, so a caller that needs both asks the repository once."""
    if run.status != "needs_you":
        return None
    return row_at(rows, run.park_path)


def park_row_of(ports: RunReadPorts, run: Run) -> StepRun | None:
    """The row this Run is parked on, for `RunSummaryOut.of`'s two row arguments (4.9, and
    the `skip_step` offer's own `park_row_status` — Operator, 2026-09-26).

    `None` whenever there is nothing useful to look up: the Run is not `needs_you`, no
    `StepRunRepository` was wired (4.4's own read ports), or — a stored Run should never
    reach this, but a read model does not assert it — the row `park_path` names is gone.
    """
    if ports.steps is None:
        return None
    return park_row_in(run, run_rows(ports, run))


def park_row_kind_of(ports: RunReadPorts, run: Run) -> str | None:
    """The parked row's `kind` alone — `park_row_of`'s answer read for the one field 4.9
    named, kept for the callers that ask only that."""
    row = park_row_of(ports, run)
    return row.kind if row is not None else None
