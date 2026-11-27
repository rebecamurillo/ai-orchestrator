"""The SQLAlchemy adapter for the `ProjectPackageRepository` port.

It mirrors `tests/unit/fakes/packages.py`: `put` inserts or replaces by `project_id`, and
`delete` of a missing row is a no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from orchestrator.domain.entities.project_package import PackageDeclaration, ProjectPackage
from orchestrator.domain.errors import Conflict
from orchestrator.infrastructure.db.models.project_package import ProjectPackageRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session


def to_entity(row: ProjectPackageRow) -> ProjectPackage:
    return ProjectPackage(
        id=row.id,
        project_id=row.project_id,
        repository_id=row.repository_id,
        path=row.path,
        ref=row.ref,
        sha=row.sha,
        name=row.name,
        declaration=PackageDeclaration.model_validate(row.declaration),
        installed_at=row.installed_at,
    )


class SQLAlchemyProjectPackageRepository:
    """Stored package installs, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _row(self, project_id: UUID) -> ProjectPackageRow | None:
        statement = select(ProjectPackageRow).where(ProjectPackageRow.project_id == project_id)
        return self._session.scalars(statement).first()

    def get(self, project_id: UUID) -> ProjectPackage | None:
        row = self._row(project_id)
        return None if row is None else to_entity(row)

    def put(self, package: ProjectPackage) -> None:
        row = self._row(package.project_id)
        if row is None:
            row = ProjectPackageRow(id=package.id, project_id=package.project_id)
            self._session.add(row)
        row.repository_id = package.repository_id
        row.path = package.path
        row.ref = package.ref
        row.sha = package.sha
        row.name = package.name
        row.declaration = package.declaration.model_dump(mode="json")
        row.installed_at = package.installed_at
        try:
            self._session.flush()
        except IntegrityError as error:
            raise Conflict(
                f"the package of project {package.project_id} was written by a concurrent"
                " install; nothing stored"
            ) from error

    def delete(self, project_id: UUID) -> None:
        row = self._row(project_id)
        if row is not None:
            self._session.delete(row)
            self._session.flush()

    def list_by_name(self, name: str) -> list[ProjectPackage]:
        statement = (
            select(ProjectPackageRow)
            .where(ProjectPackageRow.name == name)
            .order_by(ProjectPackageRow.installed_at)
        )
        return [to_entity(row) for row in self._session.scalars(statement).all()]
