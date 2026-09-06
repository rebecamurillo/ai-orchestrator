"""Reading one Run's environment: the facts a git executor is handed, out of storage.

AD-9 closes `StepContext`'s field list and AD-8 says an executor never touches a repository,
so the reads that answer "where is this Repository's clone, what does it install, what is its
default branch" happen *here* — in infrastructure, on a session of their own — and the result
travels to the executor as a frozen `RunEnvironment` inside `StepPorts`
(`application/steps/context.py` says why that is the field AD-9 leaves open).

A session of its own, opened and closed around the three reads, for the same reason
`open_writer_ports` opens one per durable step: a row that runs for forty minutes must not
hold a connection while it does, and this read happens before the executor starts, not during
it.

A Run, Project or Repository that is not there answers `None` rather than raising. The
executor then refuses with the wiring error `require_env` names, which is an `internal` park
with a class name on it (`steps/registry.py`) — the honest outcome for a Run whose Repository
was deleted underneath it, and not a traceback in the middle of a durable step.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.steps.context import RunEnvironment
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
)
from orchestrator.infrastructure.db.writers import SessionFactory

#: The Run input every dev-loop Template binds its spec folder under (`epic@1`, `story@1`).
#: `repo-init@1` declares none, and `None` is what `git.commit` reads as "stage everything".
SPEC_FOLDER_INPUT = "spec_folder"


def read_run_environment(
    session_factory: SessionFactory, bmad_version: str, run_id: UUID
) -> RunEnvironment | None:
    """One Run's Project, Repository and worktree state, as one frozen value."""
    session = session_factory()
    try:
        run = SQLAlchemyRunRepository(session).get(run_id)
        if run is None:
            return None
        project = SQLAlchemyProjectRepository(session).get(run.project_id)
        repository = SQLAlchemyRepositoryRepository(session).get(run.repository_id)
        if project is None or repository is None:
            return None
        spec_folder = run.inputs.get(SPEC_FOLDER_INPUT)
        return RunEnvironment(
            run_id=run.id,
            project_slug=project.slug,
            repository_slug=repository.slug,
            repository_url=repository.url,
            default_branch=repository.default_branch,
            install_command=repository.install_command,
            bmad_version=bmad_version,
            spec_folder=str(spec_folder) if spec_folder else None,
            worktrees=run.worktrees,
            compare_urls=run.compare_urls,
            accepted_paths=run.accepted_paths,
        )
    finally:
        session.close()
