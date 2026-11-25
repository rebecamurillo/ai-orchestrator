"""Create and cancel an initiative (SPEC CAP-3; AD-36 "Writers", AD-37 "Branches").

A create pushes `spec/{slug}` on the hub, then inserts the initiative and its spec Run in one
unit of work; when `create_run` refuses, nothing is committed and the branch this call made is
deleted. A cancel locks the initiative first, cancels every live Run through `signal_run`
(its own unit of work), then deletes the branch once every Run has ended.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.templates.inputs import declared_inputs
from orchestrator.application.templates.lines import load_with_lines
from orchestrator.application.use_cases import templates as template_use_cases
from orchestrator.application.use_cases.clone_check import BASE_DIRECTORY
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    create_run,
)
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.domain.entities.initiative import (
    FrozenSequence,
    FrozenWorkflow,
    Initiative,
    InitiativeKey,
)
from orchestrator.domain.entities.project import Project, slugify
from orchestrator.domain.entities.project_package import ProjectPackage
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git, GitError
from orchestrator.domain.ports.initiative_runs import InitiativeRunReads
from orchestrator.domain.ports.initiatives import InitiativeAdvanceRepository, InitiativeRepository
from orchestrator.domain.ports.packages import ProjectPackageRepository
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.domain.ports.repositories import ProjectRepository, RepositoryRepository
from orchestrator.domain.ports.templates import TemplateVersionRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork
from orchestrator.domain.statuses import TERMINAL_RUN
from orchestrator.domain.values import Signal

SPEC_BRANCH_PREFIX = "spec"
#: Refusals whose one positional message can be extended; any other class keeps its own text.
_PLAIN_REFUSALS = (Conflict, Invalid, NotFound)


@dataclass(frozen=True)
class InitiativePorts:
    """Everything the initiative use cases reach the outside world through."""

    initiatives: InitiativeRepository
    advances: InitiativeAdvanceRepository
    projects: ProjectRepository
    repositories: RepositoryRepository
    packages: ProjectPackageRepository
    templates: TemplateVersionRepository
    runs: InitiativeRunReads
    git: Git
    branches: RemoteBranches
    create_run: CreateRunPorts
    signals: SignalPorts
    uow: UnitOfWork
    clock: Clock
    work_dir: Path


class _SlugTaken(Exception):
    """The initiative insert lost a race for the slug."""


def _branch(slug: str) -> str:
    return f"{SPEC_BRANCH_PREFIX}/{slug}"


def _base_dir(ports: InitiativePorts, project: Project, hub: Repository) -> Path:
    return ports.work_dir / project.slug / hub.slug / BASE_DIRECTORY


def _require_text(value: str, field: str) -> None:
    if not value.strip():
        raise Invalid(f"{field} must not be blank")


def _hub_of(ports: InitiativePorts, project: Project) -> tuple[ProjectPackage, Repository]:
    package = ports.packages.get(project.id)
    if package is None:
        raise Conflict(f"no package installed on project {project.name}")
    hub = ports.repositories.get(package.repository_id)
    if hub is None:
        raise NotFound(f"no repository {package.repository_id}")
    return package, hub


def _refuse_taken_slug(ports: InitiativePorts, hub: Repository, slug: str) -> None:
    holder = ports.initiatives.get_open_by_slug(hub.id, slug)
    if holder is not None:
        raise Conflict(f"slug {slug} is used by an open initiative: {holder.name} ({holder.id})")
    for earlier in ports.initiatives.list_by_slug(hub.id, slug):
        if earlier.branch_cleanup_error is not None:
            raise Conflict(
                f"slug {slug} waits for its branch cleanup: {earlier.branch_cleanup_error}"
            )
    if ports.git.ls_remote(hub.url, _branch(slug)) is not None:
        raise Conflict(
            f"branch {_branch(slug)} already exists on the hub; delete it or choose another name"
        )


def _freeze(ports: InitiativePorts, package: ProjectPackage) -> FrozenSequence:
    declaration = package.declaration
    workflows = tuple(
        FrozenWorkflow(
            workflow=entry.workflow,
            template=entry.template,
            version=entry.version
            if entry.version is not None
            else template_use_cases.latest_version(ports.templates, entry.template),
            type=entry.type,
            shown_as=entry.shown_as,
            steps=entry.steps,
        )
        for entry in declaration.sequence
    )
    return FrozenSequence(
        package=declaration.name,
        sha=package.sha,
        workflows=workflows,
        gate=declaration.gate,
        status_map=dict(declaration.status_map),
    )


def _spec_inputs(
    ports: InitiativePorts, workflow: FrozenWorkflow, slug: str, first_message: str
) -> dict[str, str]:
    """The declared subset of what the spec Run is told; `create_run` binds the folder."""
    stored = ports.templates.get(workflow.template, workflow.version)
    if stored is None:
        return {}
    loaded = load_with_lines(stored.yaml)
    declared = declared_inputs(loaded.root) if loaded.root is not None else {}
    offered = {"slug": slug, "branch": _branch(slug), "first_turn": first_message}
    return {name: value for name, value in offered.items() if name in declared}


def create_initiative(
    ports: InitiativePorts, project_id: UUID, *, name: str, first_message: str
) -> Initiative:
    """Branch `spec/{slug}` from the hub's default branch, then store the initiative and its Run."""
    project = ports.projects.get(project_id)
    if project is None:
        raise NotFound(f"no project {project_id}")
    _require_text(name, "name")
    _require_text(first_message, "first_message")
    package, hub = _hub_of(ports, project)
    slug = slugify(name)
    _refuse_taken_slug(ports, hub, slug)
    tip = ports.git.ls_remote(hub.url, hub.default_branch)
    if tip is None:
        raise Conflict(f"branch {hub.default_branch} is not on the hub's remote")
    base_dir = _base_dir(ports, project, hub)
    if not ports.git.base_exists(base_dir):
        ports.git.clone_base(hub.url, base_dir)
    ports.git.fetch_base(base_dir, hub.default_branch)
    ports.branches.create_remote_branch(base_dir, _branch(slug), tip.sha)

    now = ports.clock.now()
    initiative = Initiative(
        id=new_id(),
        project_id=project.id,
        repository_id=hub.id,
        slug=slug,
        name=name,
        first_message=first_message,
        sequence=_freeze(ports, package),
        created_at=now,
        updated_at=now,
    )
    try:
        _create_spec_run(ports, project, hub, initiative)
    except Exception as error:
        ports.uow.rollback()
        if ports.initiatives.get(initiative.id) is not None:
            raise  # `create_run` failed after its commit: the stored Run still needs the branch
        _undo_create(ports, base_dir, initiative, error)
        raise
    stored = ports.initiatives.get(initiative.id)
    assert stored is not None
    return stored


def _create_spec_run(
    ports: InitiativePorts, project: Project, hub: Repository, initiative: Initiative
) -> None:
    def add() -> None:
        try:
            ports.initiatives.add(initiative)
        except ValueError as error:
            raise _SlugTaken from error

    first = initiative.sequence.workflows[0]
    create_run(
        ports.create_run,
        CreateRunRequest(
            template_name=first.template,
            template_version=first.version,
            project_id=project.id,
            repository_id=hub.id,
            base_branch=hub.default_branch,
            budget_usd=project.default_budget_usd,
            harness=project.default_harness,
            model=project.default_model,
            inputs=_spec_inputs(ports, first, initiative.slug, initiative.first_message),
            conflict_consent=True,
            initiative=InitiativeKey(initiative_id=initiative.id, round=1, position=0),
        ),
        before_commit=add,
    )


def _undo_create(
    ports: InitiativePorts, base_dir: Path, initiative: Initiative, error: Exception
) -> None:
    """Delete the branch this call pushed, and turn a lost slug race into the holder's refusal."""
    branch = _branch(initiative.slug)
    try:
        ports.branches.delete_remote_branch(base_dir, branch)
    except GitError as failure:
        note = f"; branch {branch} was not deleted: {failure.output}"
        if isinstance(error, _SlugTaken):
            raise Conflict(f"slug {initiative.slug} is used by an open initiative{note}") from error
        if type(error) in _PLAIN_REFUSALS:
            raise type(error)(f"{error}{note}") from error
        error.add_note(note.removeprefix("; "))
        raise error from failure
    if isinstance(error, _SlugTaken):
        raise _holder_refusal(ports, initiative) from error


def _holder_refusal(ports: InitiativePorts, initiative: Initiative) -> Conflict:
    holder = ports.initiatives.get_open_by_slug(initiative.repository_id, initiative.slug)
    if holder is None:
        return Conflict(f"slug {initiative.slug} is used by an open initiative")
    return Conflict(
        f"slug {initiative.slug} is used by an open initiative: {holder.name} ({holder.id})"
    )


def cancel_initiative(ports: InitiativePorts, initiative_id: UUID) -> Initiative:
    """Cancel every live Run, then delete `spec/{slug}`; a second call retries what is left."""
    initiative = ports.initiatives.get_for_update(initiative_id)
    if initiative is None:
        raise NotFound(f"no initiative {initiative_id}")
    if initiative.pr_merged_at is not None:
        raise Conflict("done initiatives are not cancelled")
    live = _live(ports, initiative)
    if initiative.cancelled_at is not None and not live and initiative.branch_cleanup_error is None:
        raise Conflict("already cancelled")
    if initiative.cancelled_at is None:
        now = ports.clock.now()
        initiative = initiative.model_copy(update={"cancelled_at": now, "updated_at": now})
        ports.initiatives.update(initiative)
    ports.uow.commit()

    for run in live:
        try:
            signal_run(ports.signals, run.id, Signal(kind="cancel"))
        except Conflict:
            continue  # ended by itself meanwhile: the re-read below decides
    return _clean_branch(ports, initiative_id)


def _live(ports: InitiativePorts, initiative: Initiative) -> list[Run]:
    return [
        run
        for run in ports.runs.list_for_initiative(initiative.id)
        if run.status not in TERMINAL_RUN
    ]


def _clean_branch(ports: InitiativePorts, initiative_id: UUID) -> Initiative:
    locked = ports.initiatives.get_for_update(initiative_id)
    assert locked is not None
    remaining = _live(ports, locked)
    error: str | None
    if remaining:
        error = f"Run {remaining[0].id} still stopping"
    else:
        error = _delete_branch(ports, locked)
    cleaned = locked.model_copy(
        update={"branch_cleanup_error": error, "updated_at": ports.clock.now()}
    )
    ports.initiatives.update(cleaned)
    ports.uow.commit()
    return cleaned


def _delete_branch(ports: InitiativePorts, initiative: Initiative) -> str | None:
    project = ports.projects.get(initiative.project_id)
    hub = ports.repositories.get(initiative.repository_id)
    assert project is not None
    assert hub is not None
    try:
        ports.branches.delete_remote_branch(
            _base_dir(ports, project, hub), _branch(initiative.slug)
        )
    except GitError as failure:
        return failure.output
    return None
