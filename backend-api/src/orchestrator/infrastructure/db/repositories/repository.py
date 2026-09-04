"""The SQLAlchemy adapter for the `RepositoryRepository` port.

Mirrors `infrastructure/db/repositories/projects.py`: entities in, rows out, and the two
JSON columns (`test_globs`, `clone_check`) are rebuilt rather than mutated in place on an
`update` — SQLAlchemy does not track a mutation inside a JSON value, and the write would be
silently dropped.

The session is the one the unit of work opened, passed in rather than looked up, so a
repository's reads and writes share the caller's transaction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.infrastructure.db.models.repository import RepositoryRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

#: The keys of the `clone_check` JSON object, named once so row and entity cannot drift.
STATUS_KEY = "status"
AT_KEY = "at"
OUTPUT_KEY = "output"
BMAD_VERSION_KEY = "bmad_version"

#: The fields `update` writes back. `id`, `project_id`, `slug` and `created_at` are not
#: among them: none of them is editable once the Repository is stored.
MUTABLE_FIELDS = (
    "url",
    "default_branch",
    "install_command",
    "quality_gate_command",
    "unit_test_command",
    "package_manager",
    "updated_at",
)


def clone_check_json(clone_check: CloneCheck) -> dict[str, Any]:
    """`clone_check` as the `jsonb` column holds it. `at` is `None` until 2.3 writes one."""
    return {
        STATUS_KEY: clone_check.status,
        AT_KEY: clone_check.at.isoformat() if clone_check.at is not None else None,
        OUTPUT_KEY: clone_check.output,
        BMAD_VERSION_KEY: clone_check.bmad_version,
    }


def clone_check_from_entity(data: dict[str, Any]) -> CloneCheck:
    """`clone_check` as the domain entity every layer above works with.

    Pydantic parses the stored ISO string back into a `datetime` on construction; nothing
    here has to do that by hand.
    """
    return CloneCheck(
        status=data[STATUS_KEY],
        at=data[AT_KEY],
        output=data[OUTPUT_KEY],
        bmad_version=data[BMAD_VERSION_KEY],
    )


def to_entity(row: RepositoryRow) -> Repository:
    """A row as the domain entity every layer above works with."""
    return Repository(
        id=row.id,
        project_id=row.project_id,
        slug=row.slug,
        url=row.url,
        default_branch=row.default_branch,
        install_command=row.install_command,
        quality_gate_command=row.quality_gate_command,
        unit_test_command=row.unit_test_command,
        test_globs=tuple(row.test_globs),
        package_manager=row.package_manager,
        clone_check=clone_check_from_entity(row.clone_check),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class SQLAlchemyRepositoryRepository:
    """Stored Repositories, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, repository: Repository) -> None:
        self._session.add(
            RepositoryRow(
                id=repository.id,
                project_id=repository.project_id,
                slug=repository.slug,
                url=repository.url,
                default_branch=repository.default_branch,
                install_command=repository.install_command,
                quality_gate_command=repository.quality_gate_command,
                unit_test_command=repository.unit_test_command,
                test_globs=list(repository.test_globs),
                package_manager=repository.package_manager,
                clone_check=clone_check_json(repository.clone_check),
                created_at=repository.created_at,
                updated_at=repository.updated_at,
            )
        )

    def get(self, repository_id: UUID) -> Repository | None:
        row = self._session.get(RepositoryRow, repository_id)
        return None if row is None else to_entity(row)

    def list_by_project(self, project_id: UUID) -> list[Repository]:
        rows = self._session.scalars(
            select(RepositoryRow)
            .where(RepositoryRow.project_id == project_id)
            .order_by(RepositoryRow.created_at, RepositoryRow.id)
        ).all()
        return [to_entity(row) for row in rows]

    def update(self, repository: Repository) -> None:
        row = self._session.get(RepositoryRow, repository.id)
        if row is None:
            raise ValueError(f"no repository with id {repository.id} is stored")
        for name in MUTABLE_FIELDS:
            setattr(row, name, getattr(repository, name))
        # the two JSON columns are rebuilt rather than mutated in place: SQLAlchemy does not
        # track a mutation inside a JSON value, and the update would be silently dropped
        row.test_globs = list(repository.test_globs)
        row.clone_check = clone_check_json(repository.clone_check)
