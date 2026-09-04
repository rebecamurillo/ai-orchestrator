"""The SQLAlchemy adapter for the `ProjectRepository` port.

It mirrors `tests/unit/fakes/projects.py`, which is what every use-case test runs against:
`list()` comes back ordered by `name`, a miss is `None` rather than an error, and `update`
refuses an id it does not hold. Anything this class decided that the fake did not would
only ever surface against a real database.

The session is the one the unit of work opened, passed in rather than looked up: a
repository that made its own session would write outside the caller's transaction, and a
`commit()` on the unit of work would not include it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import select

from orchestrator.domain.entities.project import EncryptedEnvVar, Project
from orchestrator.infrastructure.db.models.project import ProjectRow

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.orm import Session

#: The keys of one `env_vars_enc` element, named once so row and entity cannot drift.
ENV_NAME_KEY = "name"
ENV_VALUE_KEY = "value_enc"

#: The fields `update` writes back. `id`, `slug` and `created_at` are not among them.
MUTABLE_FIELDS = (
    "name",
    "context_text",
    "log_prompt_content",
    "updated_at",
)


def to_entity(row: ProjectRow) -> Project:
    """A row as the domain entity every layer above works with."""
    return Project(
        id=row.id,
        slug=row.slug,
        name=row.name,
        context_text=row.context_text,
        context_paths=tuple(row.context_paths),
        env_vars_enc=tuple(
            EncryptedEnvVar(name=item[ENV_NAME_KEY], value_enc=item[ENV_VALUE_KEY])
            for item in row.env_vars_enc
        ),
        log_prompt_content=row.log_prompt_content,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def env_vars_json(project: Project) -> list[dict[str, Any]]:
    """`env_vars_enc` as the `jsonb` column holds it, in the order the Operator typed."""
    return [
        {ENV_NAME_KEY: variable.name, ENV_VALUE_KEY: variable.value_enc}
        for variable in project.env_vars_enc
    ]


class SQLAlchemyProjectRepository:
    """Stored Projects, over one open session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, project: Project) -> None:
        self._session.add(
            ProjectRow(
                id=project.id,
                slug=project.slug,
                name=project.name,
                context_text=project.context_text,
                context_paths=list(project.context_paths),
                env_vars_enc=env_vars_json(project),
                log_prompt_content=project.log_prompt_content,
                created_at=project.created_at,
                updated_at=project.updated_at,
            )
        )

    def get(self, project_id: UUID) -> Project | None:
        row = self._session.get(ProjectRow, project_id)
        return None if row is None else to_entity(row)

    def get_by_slug(self, slug: str) -> Project | None:
        row = self._session.scalars(select(ProjectRow).where(ProjectRow.slug == slug)).first()
        return None if row is None else to_entity(row)

    def list(self) -> list[Project]:
        rows = self._session.scalars(select(ProjectRow).order_by(ProjectRow.name)).all()
        return [to_entity(row) for row in rows]

    def update(self, project: Project) -> None:
        row = self._session.get(ProjectRow, project.id)
        if row is None:
            raise ValueError(f"no project with id {project.id} is stored")
        for name in MUTABLE_FIELDS:
            setattr(row, name, getattr(project, name))
        # the two JSON columns are rebuilt rather than mutated in place: SQLAlchemy does not
        # track a mutation inside a JSON value, and the update would be silently dropped
        row.context_paths = list(project.context_paths)
        row.env_vars_enc = env_vars_json(project)
