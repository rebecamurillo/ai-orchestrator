"""One Project, its hub Repository and a fixture package in `FakeGit`, on the shared fakes."""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.use_cases.packages import SOURCE_PACKAGE, PackagePorts
from orchestrator.domain.entities.project import Project, slugify
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from tests.unit.application.package_fixtures import (
    PATH,
    SHA,
    build_text,
    merge_text,
    package_text,
    spec_text,
)
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.packages import FakeProjectPackageRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

URL = "https://github.com/org/hub.git"
WORK = Path("/work")


def a_project(projects: FakeProjectRepository, name: str) -> Project:
    clock = FakeClock()
    project = Project(
        id=new_id(),
        slug=slugify(name),
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=clock.now(),
        updated_at=clock.now(),
    )
    projects.add(project)
    return project


def a_repository(project: Project, url: str = URL) -> Repository:
    clock = FakeClock()
    return Repository(
        id=new_id(),
        project_id=project.id,
        slug="hub",
        url=url,
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="other",
        clone_check=CloneCheck.pending(),
        created_at=clock.now(),
        updated_at=clock.now(),
    )


def files(package: str | None = None, **texts: str) -> dict[tuple[str, str], str]:
    """The fixture package's files at `SHA`."""
    content = {
        f"{PATH}/package.yaml": package or package_text(),
        f"{PATH}/templates/spec.yaml": spec_text(),
        f"{PATH}/templates/merge.yaml": merge_text(),
    }
    content.update({f"{PATH}/{name}": text for name, text in texts.items()})
    return {(SHA, path): text for path, text in content.items()}


class World:
    """The ports of one package install, and the project and hub it targets."""

    def __init__(self, content: dict[tuple[str, str], str] | None = None) -> None:
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.packages = FakeProjectPackageRepository()
        self.templates = FakeTemplateVersionRepository(
            [
                TemplateVersion(
                    name="shipped-build",
                    version=1,
                    yaml=build_text(),
                    hash="h",
                    source="shipped",
                )
            ]
        )
        self.git = FakeGit(refs={"main": SHA}, files=content if content is not None else files())
        self.uow = FakeUnitOfWork()
        self.uow.__enter__()
        self.project = a_project(self.projects, "Familio")
        self.hub = a_repository(self.project)
        self.repositories.add(self.hub)

    @property
    def ports(self) -> PackagePorts:
        return PackagePorts(
            projects=self.projects,
            repositories=self.repositories,
            packages=self.packages,
            templates=self.templates,
            git=self.git,
            uow=self.uow,
            clock=FakeClock(),
            work_dir=WORK,
        )

    def another_project(self, name: str, url: str = URL) -> tuple[Project, Repository]:
        project = a_project(self.projects, name)
        repository = a_repository(project, url)
        self.repositories.add(repository)
        return project, repository

    def stored(self) -> list[tuple[str, int]]:
        return sorted(k for k, v in self.templates.versions.items() if v.source == SOURCE_PACKAGE)
