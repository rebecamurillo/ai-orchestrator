"""In-memory `ProjectPackageRepository` — the one fake for that port (AD-18). Reuse it."""

from __future__ import annotations

from uuid import UUID

from orchestrator.domain.entities.project_package import ProjectPackage


class FakeProjectPackageRepository:
    """Stored installs in a dictionary, keyed by Project id; `put` replaces."""

    def __init__(self, packages: list[ProjectPackage] | None = None) -> None:
        self.packages: dict[UUID, ProjectPackage] = {}
        self.puts = 0
        self.deletes = 0
        for package in packages or []:
            self.put(package)
        self.puts = 0

    def get(self, project_id: UUID) -> ProjectPackage | None:
        return self.packages.get(project_id)

    def put(self, package: ProjectPackage) -> None:
        self.puts += 1
        self.packages[package.project_id] = package

    def delete(self, project_id: UUID) -> None:
        self.deletes += 1
        self.packages.pop(project_id, None)

    def list_by_name(self, name: str) -> list[ProjectPackage]:
        found = [p for p in self.packages.values() if p.name == name]
        return sorted(found, key=lambda package: package.installed_at)
