"""The `ProjectPackageRepository` port: the one installed package of each Project (AD-39)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from orchestrator.domain.entities.project_package import ProjectPackage


@runtime_checkable
class ProjectPackageRepository(Protocol):
    """Stored package installs, one per Project."""

    def get(self, project_id: UUID) -> ProjectPackage | None:
        """The Project's install, or `None`."""
        ...

    def put(self, package: ProjectPackage) -> None:
        """Insert the install, or replace the Project's existing one."""
        ...

    def delete(self, project_id: UUID) -> None:
        """Remove the Project's install; a Project with none is a no-op."""
        ...

    def list_by_name(self, name: str) -> list[ProjectPackage]:
        """Every install of a package with this name, oldest first."""
        ...
