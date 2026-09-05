"""In-memory `ProjectRepository` — the one fake for that port (AD-18). Do not write another.

It holds entities, not rows, and it mirrors the two things the SQLAlchemy adapter's table
enforces: `list()` comes back ordered by `name`, and `add`/`update` refuse the cases the
unique index and the primary key would refuse in the database. A fake that accepted a
duplicate id would let a use case that never checked pass its tests and fail on the first
real insert.
"""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository


class FakeProjectRepository:
    """Stored Projects in a dictionary, keyed by id."""

    def __init__(self, projects: list[Project] | None = None) -> None:
        self.projects: dict[UUID, Project] = {}
        for project in projects or []:
            self.add(project)

    def add(self, project: Project) -> None:
        if project.id in self.projects:
            raise ValueError(f"a project with id {project.id} is already stored")
        if self.get_by_slug(project.slug) is not None:
            raise ValueError(f"a project with slug {project.slug!r} is already stored")
        self.projects[project.id] = project

    def get(self, project_id: UUID) -> Project | None:
        return self.projects.get(project_id)

    def get_by_slug(self, slug: str) -> Project | None:
        return next((p for p in self.projects.values() if p.slug == slug), None)

    def list(self) -> list[Project]:
        return sorted(self.projects.values(), key=lambda project: project.name)

    def update(self, project: Project) -> None:
        if project.id not in self.projects:
            raise ValueError(f"no project with id {project.id} is stored")
        self.projects[project.id] = project


class FakeRepositoryRepository:
    """Stored Repositories in a dictionary, keyed by id."""

    def __init__(self, repositories: list[Repository] | None = None) -> None:
        self.repositories: dict[UUID, Repository] = {}
        for repository in repositories or []:
            self.add(repository)

    def add(self, repository: Repository) -> None:
        if repository.id in self.repositories:
            raise ValueError(f"a repository with id {repository.id} is already stored")
        self.repositories[repository.id] = repository

    def get(self, repository_id: UUID) -> Repository | None:
        return self.repositories.get(repository_id)

    def list_by_project(self, project_id: UUID) -> list[Repository]:
        return sorted(
            (r for r in self.repositories.values() if r.project_id == project_id),
            key=lambda repository: repository.created_at,
        )

    def update(self, repository: Repository) -> None:
        if repository.id not in self.repositories:
            raise ValueError(f"no repository with id {repository.id} is stored")
        self.repositories[repository.id] = repository
