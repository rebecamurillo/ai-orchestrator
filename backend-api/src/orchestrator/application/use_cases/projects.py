"""Creating, reading and updating a Project — and decrypting its variables for a Run.

Six rules are decided here, and nowhere else:

- **A value is encrypted before it is stored, and decrypted only to be masked or exported.**
  The `Crypto` port does the work; this module holds no key (AD-5). Nothing returned by any
  function here except `decrypt_env_vars` carries a plaintext value.
- **`PUT` replaces the whole variable set.** An entry carrying a value is encrypted afresh;
  an entry without one copies the stored ciphertext verbatim, so a keep never re-encrypts
  and never decrypts; a stored name the payload does not mention is dropped. An entry
  without a value naming a variable that is not stored has nothing to keep, and is refused
  as `Invalid` rather than stored empty or silently dropped — either of those would lose
  what the Operator meant without saying so.
- **A name is unique, and a conflict is reported as one.** Renaming a Project to the name
  it already has is not a conflict.
- **A slug is derived at creation and never changes.** It names the Project's directory
  under `/work` (AD-14), so a rename must not move clones the Runs are using; a collision
  is numbered.
- **A missing Project is a `NotFound`.** The repository answers `None`; turning that into an
  outcome the API can report is a rule, which is why it lives here and not in the adapter.
- **An unstated `log_prompt_content` means two different things.** On a create it is the
  instance default `LOG_PROMPT_CONTENT_DEFAULT` (FR-2); on an update it is the value already
  stored, because a `PUT` that leaves the field out is not a request to reset it. Only these
  two functions know which case they are in, so the resolution happens here rather than in
  the payload schema.

Masking is over the plaintext, not the ciphertext, so every read decrypts what it is about
to hide. That is the cost of showing the Operator the four characters they typed.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from uuid import UUID

from orchestrator.domain.entities.project import (
    EncryptedEnvVar,
    Project,
    ProjectView,
    numbered_slug,
    slugify,
)
from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    CloneCheck,
    PackageManager,
    Repository,
    merge_test_globs,
    repo_slug,
)
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.crypto import Crypto
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.repositories import ProjectRepository, RepositoryRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork

#: The first suffix a colliding slug is given: `my-website`, then `my-website-2`.
FIRST_SLUG_SUFFIX = 2

#: Said back to the Operator when a keep names a variable that is not stored.
NO_STORED_VALUE_REASON = "no stored value to keep"


@dataclass(frozen=True)
class ProjectPorts:
    """Everything these use cases reach the outside world through.

    The unit of work is already open: whoever built this object owns the transaction
    boundary, and leaving that scope without a `commit()` discards the work.
    """

    uow: UnitOfWork
    projects: ProjectRepository
    crypto: Crypto
    clock: Clock
    #: `None` only for the frozen Project-only tests that construct `ProjectPorts` without
    #: it; `api/providers.py` always supplies a real adapter, so only a `ProjectPorts` built
    #: outside the router path can ever reach a repository use case without one.
    repositories: RepositoryRepository | None = None
    #: `None` for the same reason as `repositories`: a `ProjectPorts` built outside the
    #: router path has no git adapter. `api/providers.py` always supplies one, so only the
    #: clone check ever reads it, and it says so rather than silently checking nothing.
    git: Git | None = None


@dataclass(frozen=True)
class EnvVarInput:
    """One requested variable. `value is None` means "keep whatever is stored"."""

    name: str
    value: str | None = None


@dataclass(frozen=True)
class ProjectDraft:
    """What the Operator asked for, with the shape rules already applied by the API."""

    name: str
    #: `None` means the payload did not state one — see the module docstring.
    log_prompt_content: bool | None = None
    context_text: str = ""
    context_paths: tuple[str, ...] = ()
    env_vars: tuple[EnvVarInput, ...] = field(default_factory=tuple)


def create_project(
    ports: ProjectPorts, draft: ProjectDraft, *, log_prompt_content_default: bool
) -> ProjectView:
    """Store a new Project and return it masked."""
    _refuse_duplicate_name(ports.projects, draft.name)
    now = ports.clock.now()
    project = Project(
        id=new_id(),
        slug=_free_slug(ports.projects, draft.name),
        name=draft.name,
        context_text=draft.context_text,
        context_paths=draft.context_paths,
        env_vars_enc=_resolve_env_vars((), draft.env_vars, ports.crypto),
        log_prompt_content=_stated(draft.log_prompt_content, log_prompt_content_default),
        created_at=now,
        updated_at=now,
    )
    ports.projects.add(project)
    ports.uow.commit()
    return _masked(project, ports.crypto)


def update_project(ports: ProjectPorts, project_id: UUID, draft: ProjectDraft) -> ProjectView:
    """Replace a stored Project's editable fields, keeping its id, slug and creation time.

    A `log_prompt_content` the payload did not state keeps the stored value. Resolving it
    to the instance default instead would turn every `PUT` that omits the switch into a
    silent reset of a choice the Operator made deliberately.
    """
    stored = _require(ports.projects, project_id)
    _refuse_duplicate_name(ports.projects, draft.name, excluding=stored.id)
    updated = stored.model_copy(
        update={
            "name": draft.name,
            "context_text": draft.context_text,
            "context_paths": draft.context_paths,
            "env_vars_enc": _resolve_env_vars(stored.env_vars_enc, draft.env_vars, ports.crypto),
            "log_prompt_content": _stated(draft.log_prompt_content, stored.log_prompt_content),
            "updated_at": ports.clock.now(),
        }
    )
    ports.projects.update(updated)
    ports.uow.commit()
    return _masked(updated, ports.crypto)


def get_project(ports: ProjectPorts, project_id: UUID) -> ProjectView:
    """One stored Project, masked."""
    return _masked(_require(ports.projects, project_id), ports.crypto)


def list_projects(ports: ProjectPorts) -> list[ProjectView]:
    """Every stored Project, masked, in the order the repository returns them (by name)."""
    return [_masked(project, ports.crypto) for project in ports.projects.list()]


def decrypt_env_vars(ports: ProjectPorts, project_id: UUID) -> dict[str, str]:
    """`{name: plaintext}` for the Run machinery that builds a harness environment (AD-10).

    The one function here that returns plaintext. No route reaches it, and no router
    imports this module's name for it.
    """
    project = _require(ports.projects, project_id)
    return _plaintexts(project.env_vars_enc, ports.crypto)


# ── the rules the four operations share ──────────────────────────────────────


def _stated(chosen: bool | None, fallback: bool) -> bool:
    """The switch the payload stated, or the one that applies when it stated none."""
    return fallback if chosen is None else chosen


def _require(projects: ProjectRepository, project_id: UUID) -> Project:
    stored = projects.get(project_id)
    if stored is None:
        raise NotFound(f"no project with id {project_id}")
    return stored


def _refuse_duplicate_name(
    projects: ProjectRepository, name: str, *, excluding: UUID | None = None
) -> None:
    """A name identifies a Project on the Board; two of them would be unreadable."""
    for project in projects.list():
        if project.name == name and project.id != excluding:
            raise Conflict(f"a project named {name!r} already exists")


def _free_slug(projects: ProjectRepository, name: str) -> str:
    """The name's slug, numbered until it is one no stored Project holds."""
    base = slugify(name)
    if projects.get_by_slug(base) is None:
        return base
    number = FIRST_SLUG_SUFFIX
    while projects.get_by_slug(numbered_slug(base, number)) is not None:
        number += 1
    return numbered_slug(base, number)


def _resolve_env_vars(
    stored: Iterable[EncryptedEnvVar], requested: Iterable[EnvVarInput], crypto: Crypto
) -> tuple[EncryptedEnvVar, ...]:
    """The variable set the payload asks for: values encrypted, keeps copied verbatim."""
    kept = {variable.name: variable.value_enc for variable in stored}
    resolved: list[EncryptedEnvVar] = []
    for entry in requested:
        if entry.value is None:
            if entry.name not in kept:
                raise Invalid(f"{entry.name}: {NO_STORED_VALUE_REASON}")
            resolved.append(EncryptedEnvVar(name=entry.name, value_enc=kept[entry.name]))
        else:
            resolved.append(EncryptedEnvVar(name=entry.name, value_enc=crypto.encrypt(entry.value)))
    return tuple(resolved)


def _plaintexts(stored: Iterable[EncryptedEnvVar], crypto: Crypto) -> dict[str, str]:
    return {variable.name: crypto.decrypt(variable.value_enc) for variable in stored}


def _masked(project: Project, crypto: Crypto) -> ProjectView:
    """The read model. The plaintexts are decrypted, masked, and dropped on the same line."""
    return project.view(_plaintexts(project.env_vars_enc, crypto))


# ── repository ───────────────────────────────────────────────────────────────
#
# Register the git repositories a Run works in. `POST` and `PUT` share one rule each: the
# `test_globs` merge always applies, `clone_check` is never written here, and the slug is
# derived once and never recomputed. A duplicate `url` is a `Conflict` scoped to the
# Project it was posted under — the same `url` under another Project is unremarkable.


@dataclass(frozen=True)
class RepositoryDraft:
    """What the Operator asked for, with the shape rules already applied by the API."""

    url: str
    default_branch: str
    install_command: str = ""
    quality_gate_command: str = ""
    unit_test_command: str = ""
    #: Globs the Operator asked to add, on top of `DEFAULT_TEST_GLOBS`.
    test_globs: tuple[str, ...] = ()
    package_manager: PackageManager = DEFAULT_PACKAGE_MANAGER


def add_repository(ports: ProjectPorts, project_id: UUID, draft: RepositoryDraft) -> Repository:
    """Register a Repository under a Project, its `clone_check` starting `pending`."""
    repositories = _repos(ports)
    _require(ports.projects, project_id)
    siblings = repositories.list_by_project(project_id)
    _refuse_duplicate_url(siblings, draft.url)
    now = ports.clock.now()
    repository = Repository(
        id=new_id(),
        project_id=project_id,
        slug=_free_repo_slug(siblings, draft.url),
        url=draft.url,
        default_branch=draft.default_branch,
        install_command=draft.install_command,
        quality_gate_command=draft.quality_gate_command,
        unit_test_command=draft.unit_test_command,
        test_globs=merge_test_globs(draft.test_globs),
        package_manager=draft.package_manager,
        clone_check=CloneCheck.pending(),
        created_at=now,
        updated_at=now,
    )
    repositories.add(repository)
    ports.uow.commit()
    return repository


def get_repository(ports: ProjectPorts, repository_id: UUID) -> Repository:
    """One stored Repository."""
    return _require_repository(_repos(ports), repository_id)


def list_repositories_by_project(ports: ProjectPorts, project_id: UUID) -> list[Repository]:
    """Every Repository stored under this Project, in the order they were created."""
    _require(ports.projects, project_id)
    return _repos(ports).list_by_project(project_id)


def embedded_repositories(ports: ProjectPorts, project_id: UUID) -> list[Repository]:
    """The Repositories `ProjectRead` embeds — `[]` when no repository store is attached.

    Every route that renders a `ProjectRead` (create, read, update, list) calls this rather
    than `list_repositories_by_project`: a `ProjectPorts` with `repositories is None` is the
    frozen Project-only test harnesses that predate this port (see `ProjectPorts`'s
    docstring), not a wiring bug, and a Project genuinely has no Repository to show them.
    `api/providers.py` always supplies a real adapter, so a production read still queries
    truthfully — this never silently substitutes an empty list where a real one exists.
    """
    if ports.repositories is None:
        return []
    return ports.repositories.list_by_project(project_id)


def update_repository(
    ports: ProjectPorts, repository_id: UUID, draft: RepositoryDraft
) -> Repository:
    """Replace a Repository's editable fields. Its `clone_check` and slug are untouched."""
    repositories = _repos(ports)
    stored = _require_repository(repositories, repository_id)
    siblings = repositories.list_by_project(stored.project_id)
    _refuse_duplicate_url(siblings, draft.url, excluding=stored.id)
    updated = stored.model_copy(
        update={
            "url": draft.url,
            "default_branch": draft.default_branch,
            "install_command": draft.install_command,
            "quality_gate_command": draft.quality_gate_command,
            "unit_test_command": draft.unit_test_command,
            "test_globs": merge_test_globs(draft.test_globs),
            "package_manager": draft.package_manager,
            "updated_at": ports.clock.now(),
        }
    )
    repositories.update(updated)
    ports.uow.commit()
    return updated


def _repos(ports: ProjectPorts) -> RepositoryRepository:
    """Type-narrow `ports.repositories` for mypy strict.

    `api/providers.py` always builds a `ProjectPorts` with a real adapter; a `None` here
    means a repository use case was reached through a `ProjectPorts` some other caller
    built without one — a wiring bug, reported loudly rather than as a `None` deref.
    """
    if ports.repositories is None:
        raise RuntimeError("ProjectPorts.repositories is not set: a repository use case needs it")
    return ports.repositories


def _require_repository(repositories: RepositoryRepository, repository_id: UUID) -> Repository:
    stored = repositories.get(repository_id)
    if stored is None:
        raise NotFound(f"no repository with id {repository_id}")
    return stored


def _refuse_duplicate_url(
    siblings: list[Repository],
    url: str,
    *,
    excluding: UUID | None = None,
) -> None:
    """A `url` identifies a Repository within its Project; the same one twice is a conflict.

    The same `url` under a different Project is unremarkable — a monorepo the whole team
    clones under two Projects, say — so the caller passes only that Project's Repositories.
    """
    for repository in siblings:
        if repository.url == url and repository.id != excluding:
            raise Conflict(f"a repository with url {url!r} already exists in this project")


def _free_repo_slug(siblings: list[Repository], url: str) -> str:
    """The URL's slug, numbered until it is one no Repository in this Project holds."""
    base = repo_slug(url)
    taken = {repository.slug for repository in siblings}
    if base not in taken:
        return base
    number = FIRST_SLUG_SUFFIX
    while numbered_slug(base, number) in taken:
        number += 1
    return numbered_slug(base, number)
