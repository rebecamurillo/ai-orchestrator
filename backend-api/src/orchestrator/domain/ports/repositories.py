"""The repository ports: how a use case reaches stored entities without naming a database.

One `Protocol` per entity. A repository takes and returns domain entities, never rows and
never a session: `application/` may not import `sqlalchemy` (AD-2), and a use case written
against these methods runs unchanged over the in-memory fakes in `tests/unit/fakes/` and
over the SQLAlchemy adapters in `infrastructure/db/repositories/`.

Reads return `None` for "not stored"; deciding that a missing Project is a `NotFound` is a
rule, and rules live in `application/`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository


@runtime_checkable
class ProjectRepository(Protocol):
    """Stored Projects, by id and by slug."""

    def add(self, project: Project) -> None:
        """Store a Project that does not exist yet."""
        ...

    def get(self, project_id: UUID) -> Project | None:
        """The Project with this id, or `None`."""
        ...

    def get_by_slug(self, slug: str) -> Project | None:
        """The Project with this slug, or `None` — the slug is unique per instance."""
        ...

    def list(self) -> list[Project]:
        """Every stored Project, ordered by `name`."""
        ...

    def update(self, project: Project) -> None:
        """Replace the stored Project with this one, matched on its id."""
        ...


@runtime_checkable
class RepositoryRepository(Protocol):
    """Stored Repositories, each scoped to the Project it is nested under."""

    def add(self, repository: Repository) -> None:
        """Store a Repository that does not exist yet."""
        ...

    def get(self, repository_id: UUID) -> Repository | None:
        """The Repository with this id, or `None`."""
        ...

    def list_by_project(self, project_id: UUID) -> list[Repository]:
        """Every Repository stored under this Project, ordered by creation time."""
        ...

    def update(self, repository: Repository) -> None:
        """Replace the stored Repository with this one, matched on its id."""
        ...
