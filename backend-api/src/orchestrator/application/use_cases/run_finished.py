"""`on_finished` (SPEC CAP-10, FR-30): the walker's own completion hook.

A Run that installed the method and reached `done` has just changed what
`_bmad/_config/manifest.yaml` says on the default branch's own eventual merge target — but
the Repository row reads the *last checked* version, not a live one, so without this hook
the method cell would still say
`missing` until the Operator clicked *re-run check* by hand
(`[ASSUMPTION: a completion hook re-runs the clone check so the method cell updates without a
manual re-run]`, the brief's own words). `on_finished` is the one seam this epic wires: every
other Run, and every other outcome, is a no-op. Epic 5 adds a second effect (readiness
evaluation) to this same seam rather than a second hook into the walker.

**Which Runs those are is read off the plan, never off a Template name** (Operator decision
2026-09-30: no template name hardcoded in product code). The fact this hook needs is "did
this Run install or refresh the method", and the Run's own persisted rows answer it: a
`bmad.install` row is what installs it (`application/steps/bmad_install.py`), so a Run with
one is a Run whose manifest reading is now stale. Reading the rows by kind is the pattern
`run_views_summary.py` already uses for `git.commit` and `git.push`.

Nothing here writes a Run's own status or any of its rows (AD-8); `repository.clone_check`
is the one column this module writes, through the same pure check `run_clone_check` (4.3)
uses — reused, not reimplemented, so the two can never disagree about what a check found.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.preflight.checks import BMAD_INSTALL_KIND
from orchestrator.application.use_cases.clone_check import _base, _checked
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import (
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
    StepRunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: The only Run outcome this hook acts on. `failed` and `cancelled` leave the Repository's
#: last clone check exactly as informative as it already was.
DONE = "done"


@dataclass(frozen=True)
class RunFinishedPorts:
    """Everything `on_finished` reaches the outside world through."""

    runs: RunRepository
    #: The Run's own rows — what says whether it installed the method (see the module
    #: docstring). `None` in a process that wired no step-run repository: the hook then
    #: does nothing, the same tolerance `git` below already states.
    steps: StepRunRepository | None
    repositories: RepositoryRepository
    projects: ProjectRepository
    #: `None` in a process that never wired a git adapter — the hook then does nothing
    #: rather than guessing, the same tolerance `git_adapter` (`api/providers.py`) already
    #: gives a route that does not need one.
    git: Git | None
    uow: UnitOfWork
    clock: Clock
    work_dir: Path
    bmad_version: str


def on_finished(ports: RunFinishedPorts, run_id: UUID) -> Repository | None:
    """Re-run the clone check of a finished method-installing Run's own Repository.

    `None` for every Run this hook has nothing to do for: one that installed no method, one
    that is not `done`, a Repository or Project that is gone, or a process with no git or
    step-run adapter wired. The returned `Repository` is the one this call wrote, for a test
    to assert on without a second read.
    """
    run = ports.runs.get(run_id)
    if run is None or run.status != DONE:
        return None
    if ports.git is None or ports.steps is None:
        return None
    if not _installed_the_method(ports, run_id):
        return None
    repository = ports.repositories.get(run.repository_id)
    if repository is None:
        return None
    project = ports.projects.get(repository.project_id)
    if project is None:
        return None
    base = _base(ports.work_dir, project.slug, repository.slug)
    checked = _checked(ports.git, ports.clock, repository, base, ports.bmad_version)
    ports.repositories.update(checked)
    ports.uow.commit()
    return checked


def _installed_the_method(ports: RunFinishedPorts, run_id: UUID) -> bool:
    """Whether this Run's plan held a `bmad.install` row — the one thing that makes the
    Repository's stored method version stale (see the module docstring). Read off the
    persisted rows, so a Template of any name that installs the method is covered and one
    that does not is left alone."""
    assert ports.steps is not None  # the caller returns early without one
    return any(row.kind == BMAD_INSTALL_KIND for row in ports.steps.list_for_run(run_id))
