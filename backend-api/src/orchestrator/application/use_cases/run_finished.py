"""`on_finished` (SPEC CAP-10, FR-30): the walker's own completion hook.

A `repo-init` Run that reaches `done` has just changed what `_bmad/_config/manifest.yaml`
says on the default branch's own eventual merge target — but the Repository row reads the
*last checked* version, not a live one, so without this hook the method cell would still say
`missing` until the Operator clicked *re-run check* by hand
(`[ASSUMPTION: a completion hook re-runs the clone check so the method cell updates without a
manual re-run]`, the brief's own words). `on_finished` is the one seam this epic wires: every
other Run, and every other outcome, is a no-op. Epic 5 adds a second effect (readiness
evaluation) to this same seam rather than a second hook into the walker.

Nothing here writes a Run's own status or any of its rows (AD-8); `repository.clone_check`
is the one column this module writes, through the same pure check `run_clone_check` (4.3)
uses — reused, not reimplemented, so the two can never disagree about what a check found.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.use_cases.clone_check import _base, _checked
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import (
    ProjectRepository,
    RepositoryRepository,
    RunRepository,
)
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: The only Template this hook ever acts on (AD-16). Every other Template's Run finishing
#: is a no-op today.
REPO_INIT_TEMPLATE = "repo-init"

#: The only Run outcome this hook acts on. `failed` and `cancelled` leave the Repository's
#: last clone check exactly as informative as it already was.
DONE = "done"


@dataclass(frozen=True)
class RunFinishedPorts:
    """Everything `on_finished` reaches the outside world through."""

    runs: RunRepository
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
    """Re-run a finished `repo-init` Run's own Repository clone check.

    `None` for every Run this hook has nothing to do for: not `repo-init`, not `done`, a
    Repository or Project that is gone, or a process with no git adapter wired. The returned
    `Repository` is the one this call wrote, for a test to assert on without a second read.
    """
    run = ports.runs.get(run_id)
    if run is None or run.status != DONE or run.template_name != REPO_INIT_TEMPLATE:
        return None
    if ports.git is None:
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
