"""Install, read and remove a Project's package (SPEC CAP-3, AD-39).

Install is all or nothing: every read and every check runs before the first write, and the
template versions and the record are stored in one unit of work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from orchestrator.application.packages import declaration as rules
from orchestrator.application.packages.declaration import (
    PackageInvalid,
    PackageProblem,
    ParsedEntry,
    ParsedPackage,
)
from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.use_cases import templates as template_use_cases
from orchestrator.application.use_cases.clone_check import BASE_DIRECTORY
from orchestrator.application.use_cases.template_judge import judge_text
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.project_package import (
    GateWords,
    PackageDeclaration,
    ProjectPackage,
    SequenceEntry,
)
from orchestrator.domain.entities.repository import Repository, is_valid_folder
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.clock import Clock
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.initiatives import InitiativeRepository
from orchestrator.domain.ports.packages import ProjectPackageRepository
from orchestrator.domain.ports.repositories import ProjectRepository, RepositoryRepository
from orchestrator.domain.ports.templates import TemplateVersionRepository
from orchestrator.domain.ports.unit_of_work import UnitOfWork

SOURCE_PACKAGE = "package"

PATH_RULE = (
    "path: must be one or more [A-Za-z0-9._-] segments joined by /, "
    "with no . or .. segment and no leading or trailing /"
)


@dataclass(frozen=True)
class PackagePorts:
    """Everything the package use cases reach the outside world through."""

    projects: ProjectRepository
    repositories: RepositoryRepository
    packages: ProjectPackageRepository
    templates: TemplateVersionRepository
    git: Git
    uow: UnitOfWork
    clock: Clock
    work_dir: Path
    #: `None` skips the open-initiative refusal of `remove_package`.
    initiatives: InitiativeRepository | None = None


@dataclass(frozen=True)
class _Loaded:
    """One package entry read and judged: its text and tree."""

    entry: ParsedEntry
    text: str
    parsed: ParsedTemplate


def _hub(ports: PackagePorts, project_id: UUID, repository_id: UUID) -> tuple[Project, Repository]:
    project = ports.projects.get(project_id)
    if project is None:
        raise NotFound(f"no project {project_id}")
    repository = ports.repositories.get(repository_id)
    if repository is None or repository.project_id != project_id:
        raise NotFound(f"no repository {repository_id} in project {project.slug}")
    return project, repository


def _fetch(
    ports: PackagePorts, project: Project, repository: Repository, ref: str
) -> tuple[Path, str]:
    """The base clone, brought up to `ref`, and the commit the remote answers for it."""
    remote = ports.git.ls_remote(repository.url, ref)
    if remote is None:
        raise Conflict(f"ref {ref} is not a branch of {repository.slug}'s remote")
    dest = ports.work_dir / project.slug / repository.slug / BASE_DIRECTORY
    if not ports.git.base_exists(dest):
        ports.git.clone_base(repository.url, dest)
    ports.git.fetch_base(dest, ref)
    return dest, remote.sha


def _read_template(
    ports: PackagePorts, dest: Path, sha: str, path: str, entry: ParsedEntry
) -> tuple[_Loaded | None, list[PackageProblem]]:
    file = f"{path}/{entry.template}"
    text = ports.git.read_file(dest, sha, file)
    if text is None:
        return None, [PackageProblem(file, "file not found")]
    result = judge_text(text, ports.templates)
    if result.template is None:
        return None, [PackageProblem(file, f"line {e.line}: {e.reason}") for e in result.errors]
    stem = rules.stem_of(entry.template)
    if result.template.name != stem:
        return None, [PackageProblem(file, f"name must be {stem}")]
    return _Loaded(entry, text, result.template), []


def _shipped(
    ports: PackagePorts, package_file: str, entry: ParsedEntry
) -> tuple[ParsedTemplate | None, list[PackageProblem]]:
    if entry.template not in ports.templates.names_with_source(template_use_cases.SOURCE_SHIPPED):
        return None, [PackageProblem(package_file, f"{entry.template} is not a shipped template")]
    latest = template_use_cases.latest_version(ports.templates, entry.template)
    stored = ports.templates.get(entry.template, latest)
    parsed = None if stored is None else judge_text(stored.yaml, ports.templates, latest).template
    if parsed is None:
        return None, [PackageProblem(package_file, f"{entry.template} does not validate")]
    return parsed, []


def _load(
    ports: PackagePorts, dest: Path, sha: str, path: str, pkg: ParsedPackage
) -> tuple[dict[str, _Loaded], dict[str, ParsedTemplate]]:
    """Read and judge every entry; raise one `PackageInvalid` holding every problem."""
    package_file = f"{path}/{rules.PACKAGE_FILE}"
    problems = rules.duplicate_stems(pkg.entries, path)
    files: dict[str, _Loaded] = {}
    shipped: dict[str, ParsedTemplate] = {}
    for entry in pkg.entries:
        if entry.is_file:
            loaded, found = _read_template(ports, dest, sha, path, entry)
            if loaded is not None:
                files[entry.workflow] = loaded
        else:
            parsed, found = _shipped(ports, package_file, entry)
            if parsed is not None:
                shipped[entry.workflow] = parsed
        problems += found
    if not problems:
        own = [(f"{path}/{item.entry.template}", item.parsed) for item in files.values()]
        problems += rules.gate_problems(own, pkg, path)
    if problems:
        raise PackageInvalid(problems)
    return files, shipped


def _refuse_name_clash(
    ports: PackagePorts, project_id: UUID, repository: Repository, path: str, name: str
) -> None:
    for record in ports.packages.list_by_name(name):
        if record.project_id == project_id:
            continue
        other = ports.repositories.get(record.repository_id)
        if other is None or other.url != repository.url or record.path != path:
            owner = ports.projects.get(record.project_id)
            label = record.project_id if owner is None else owner.slug
            raise Conflict(
                f"package {name} is installed on project {label} from another repository or path"
            )


def _store(ports: PackagePorts, qualified: str, sha: str, loaded: _Loaded) -> int:
    """The stored or reused version number of one package template at this commit."""
    text_hash = template_use_cases.text_hash(loaded.text)
    # One commit can hold the same package name in two folders: the sha alone does not name
    # the text, so a reuse must also match it.
    reused = ports.templates.get_by_package_sha(qualified, sha)
    if reused is not None and reused.hash == text_hash:
        return reused.version
    latest = max(ports.templates.list_versions(qualified), default=0)
    current = ports.templates.get(qualified, latest) if latest else None
    if current is not None and current.package_sha == sha and current.hash == text_hash:
        return current.version
    number = latest + 1
    ports.templates.add_version(
        TemplateVersion(
            id=new_id(),
            name=qualified,
            version=number,
            yaml=loaded.text,
            hash=text_hash,
            calls=template_use_cases.calls_of(loaded.parsed),
            created_at=ports.clock.now(),
            source=SOURCE_PACKAGE,
            package_sha=sha,
        ),
        description=loaded.parsed.description,
    )
    return number


def _sequence(
    ports: PackagePorts,
    pkg: ParsedPackage,
    sha: str,
    files: dict[str, _Loaded],
    shipped: dict[str, ParsedTemplate],
) -> tuple[SequenceEntry, ...]:
    sequence = []
    for index, entry in enumerate(pkg.entries):
        loaded = files.get(entry.workflow)
        if loaded is not None:
            template = f"{pkg.name}.{rules.stem_of(entry.template)}"
            version: int | None = _store(ports, template, sha, loaded)
            parsed = loaded.parsed
        else:
            template, version, parsed = entry.template, None, shipped[entry.workflow]
        steps = rules.entry_steps(parsed)
        sequence.append(
            SequenceEntry(
                workflow=entry.workflow,
                template=template,
                version=version,
                type=parsed.type,
                shown_as=rules.shown_as(index, parsed.type, steps),
                steps=steps,
            )
        )
    return tuple(sequence)


def install_package(
    ports: PackagePorts, project_id: UUID, *, repository_id: UUID, path: str, ref: str
) -> ProjectPackage:
    """Read the package at `ref` of the Project's hub, check it, and store it all or not at all."""
    project, repository = _hub(ports, project_id, repository_id)
    if not is_valid_folder(path):
        raise Invalid(PATH_RULE)
    dest, sha = _fetch(ports, project, repository, ref)
    package_file = f"{path}/{rules.PACKAGE_FILE}"
    text = ports.git.read_file(dest, sha, package_file)
    if text is None:
        raise PackageInvalid([PackageProblem(package_file, "file not found")])
    pkg = rules.parse_package(text, package_file)
    files, shipped = _load(ports, dest, sha, path, pkg)
    _refuse_name_clash(ports, project_id, repository, path, pkg.name)
    existing = ports.packages.get(project_id)
    record = ProjectPackage(
        id=new_id() if existing is None else existing.id,
        project_id=project_id,
        repository_id=repository_id,
        path=path,
        ref=ref,
        sha=sha,
        name=pkg.name,
        declaration=PackageDeclaration(
            name=pkg.name,
            sequence=_sequence(ports, pkg, sha, files, shipped),
            gate=GateWords(
                pass_words=pkg.pass_words, fail_words=pkg.fail_words, owners_key=pkg.owners_key
            ),
            status_map=pkg.status_map,
        ),
        installed_at=ports.clock.now(),
    )
    ports.packages.put(record)
    ports.uow.commit()
    return record


def get_package(ports: PackagePorts, project_id: UUID) -> ProjectPackage:
    """The Project's install."""
    record = ports.packages.get(project_id)
    if record is None:
        raise NotFound("no package installed")
    return record


def hub_of(ports: PackagePorts, package: ProjectPackage) -> Repository:
    """The Repository a package was read from."""
    repository = ports.repositories.get(package.repository_id)
    if repository is None:
        raise NotFound(f"no repository {package.repository_id}")
    return repository


def remove_package(ports: PackagePorts, project_id: UUID) -> None:
    """Delete the record and nothing else: a stored template version is immutable (AD-15)."""
    package = get_package(ports, project_id)
    if ports.initiatives is not None:
        open_ones = ports.initiatives.list_open_for_package(project_id, package.name)
        if open_ones:
            slugs = ", ".join(i.slug for i in open_ones)
            raise Conflict(f"refused: {len(open_ones)} open initiatives use this package — {slugs}")
    ports.packages.delete(project_id)
    ports.uow.commit()
