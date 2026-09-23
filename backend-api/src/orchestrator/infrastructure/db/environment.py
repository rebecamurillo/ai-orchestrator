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

**`crypto` is a factory, and it is optional.** The `agent` kind hands the Project's own
variables to a harness process (AD-5), and this is the one moment they are decrypted — the
`Crypto` port's own docstring says "only when a Run is about to hand the value to a harness
process", and this function is that moment. A *factory* rather than an instance because
`FernetCrypto` refuses a key that is not a Fernet key at construction, and the contract's
placeholder is not one: `walker_deps(Settings(), ...)` runs in unit tests that never
dispatch anything, and building the adapter there would fail before a Run existed. A Project
with no variables never calls it, and a caller that supplied none reads `{}` — which is what
the three-positional call every git kind's test makes has always meant.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from orchestrator.application.steps.context import ProjectContext, RunEnvironment
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ports.crypto import Crypto
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
    session_factory: SessionFactory,
    bmad_version: str,
    run_id: UUID,
    *,
    crypto: Callable[[], Crypto] | None = None,
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
        held_by_label = _held_by_label(run, SQLAlchemyRunRepository(session))
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
            run=run,
            project=_project_context(project, crypto),
            test_globs=repository.test_globs,
            held_by_label=held_by_label,
        )
    finally:
        session.close()


def _held_by_label(run: Run, runs: SQLAlchemyRunRepository) -> str | None:
    """The label of another non-terminal Run on the same (repository, partition_branch), or `None`.

    Used as the executor backstop for the race between pre-flight passing and worktree
    creation (AD-14, story 5-1). `None` when `partition_branch` is not set or no holder exists.

    # Revised: a saved Run holds no branch (multi-repo initiative S2, spine AD-14
    # amendment, 2026-09-23). Since this story's pre-flight fix, two Runs may legally
    # declare the same branch as long as at most one is in the engine at a time (a saved
    # Run no longer collides with another saved Run at creation), so a candidate with an
    # empty `engine_ref` is skipped here too — it has materialised no worktree and is not
    # who this backstop races against.
    """
    if run.partition_branch is None:
        return None
    for other in runs.list_by_repository_non_terminal(run.repository_id):
        if (
            other.id != run.id
            and other.partition_branch == run.partition_branch
            and other.engine_ref
        ):
            return f"{other.template_name} · {other.partition_branch}"
    return None


def _project_context(project: Project, crypto: Callable[[], Crypto] | None) -> ProjectContext:
    """The Project as a dispatch receives it, with its variables decrypted here and only
    here (AD-5). No key is built for a Project that declares no variable."""
    variables = project.env_vars_enc
    decrypt = crypto() if variables and crypto is not None else None
    return ProjectContext(
        context_text=project.context_text,
        context_paths=project.context_paths,
        env_vars=(
            {}
            if decrypt is None
            else {entry.name: decrypt.decrypt(entry.value_enc) for entry in variables}
        ),
        log_prompt_content=project.log_prompt_content,
    )
