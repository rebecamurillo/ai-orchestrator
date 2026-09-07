"""`worktree_gc`, the 7-day job (SPEC CAP-11, FR-9, AD-14): free a terminal Run's worktrees
and its log directory, once.

Bound the way AD-14 asks every filesystem and git effect to be: `Git.remove_worktree` is
the same idempotent call `application/use_cases/signals.py::_apply_cancel` already makes
for `cancel` (4.9), and the log directory goes through the `Workspace` port this story adds
`remove` to, rooted at `{WORK_DIR}/logs` by the caller — never a bare `shutil` here, because
`application/` may not import it (AD-2).

**Only a terminal Run, only once, only what the brief lists.** `run.status` must already be
`done`, `failed` or `cancelled` — a non-terminal Run never loses a worktree it might still
be using. `worktrees_removed` is what makes a second fire of the same day's cron (or the
e2e suite's own thrice-run stack, 4.9) a no-op: once it is `True`, this Run is never swept
again. And the brief's own scope is `Git.remove_worktree` alone — no `delete_branch` here;
4.9's `cancel` is that call's one caller, deciding a *pushed* branch stays and an unpushed
one goes at the moment the Operator cancels, which is a decision this job does not re-open
for a Run that reached `done` or `failed` on its own.

**`worktrees_removed` is a flag, not the timestamp the brief names.** Story 4.11's Design
Notes record why: `tests/unit/test_run_repository_adapter.py`'s closed set of nullable
`run` columns is frozen (hard rule 1), and a nullable `worktrees_removed_at` would have
joined it. A `NOT NULL` boolean reaches the same idempotency without touching that set, and
`run.worktrees` itself is left as history rather than cleared, so a swept Run's own record
still says which branch it worked on after the files are gone.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID

import structlog

from orchestrator.application.steps.context import RunEnvironment
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import RunRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.ports.workspace import Workspace
from orchestrator.domain.statuses import TERMINAL_RUN

log = structlog.get_logger(__name__)

#: `application/use_cases/signals.py` declares the same alias for the same reason: reading
#: one Run's Project/Repository facts without reaching into `infrastructure/` for the type
#: `infrastructure/db/environment.py::read_run_environment` actually returns (AD-2).
ReadEnvironment = Callable[[UUID], RunEnvironment | None]


@dataclass(frozen=True)
class WorktreeGcPorts:
    """What the sweep reads and writes through: the Runs, the two AD-14 ports it needs, a
    clock, and how it recovers a swept Run's own environment."""

    uow: UnitOfWork
    runs: RunRepository
    git: Git
    #: Rooted at `{WORK_DIR}/logs` by the caller (`infrastructure/jobs.py`) — this module
    #: never builds a path itself.
    logs: Workspace
    clock: Clock
    read_environment: ReadEnvironment
    work_dir: str
    retention_days: int


def run_worktree_gc(ports: WorktreeGcPorts) -> list[UUID]:
    """Every Run terminal for more than `retention_days`, swept once. Returns their ids."""
    cutoff = ports.clock.now() - timedelta(days=ports.retention_days)
    swept: list[UUID] = []
    for run in ports.runs.list():
        if _due(run, cutoff):
            _sweep(ports, run)
            swept.append(run.id)
    return swept


def _due(run: Run, cutoff: datetime) -> bool:
    """Terminal, never swept before, and ended before the retention window (module docstring)."""
    return (
        run.status in TERMINAL_RUN
        and not run.worktrees_removed
        and run.ended_at is not None
        and run.ended_at <= cutoff
    )


def _sweep(ports: WorktreeGcPorts, run: Run) -> None:
    """One Run's worktrees and logs, gone; `worktrees_removed` flipped and committed."""
    env = ports.read_environment(run.id)
    if env is not None:
        base = env.base_dir(ports.work_dir)
        for worktree in run.worktrees:
            ports.git.remove_worktree(base, Path(worktree.path))
    ports.logs.remove(str(run.id))
    ports.runs.update(run.model_copy(update={"worktrees_removed": True}))
    ports.uow.commit()
    log.info("worktree gc", run_id=str(run.id))
