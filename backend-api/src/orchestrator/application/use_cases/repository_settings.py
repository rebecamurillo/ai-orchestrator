"""Set a Repository's initiative folder: where every initiative of it lives (SPEC CAP-2)."""

from __future__ import annotations

from uuid import UUID

from orchestrator.application.use_cases import projects as project_use_cases
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.repository import Repository, is_valid_folder
from orchestrator.domain.errors import Invalid

FOLDER_RULE = (
    "initiative_folder: must be one or more [A-Za-z0-9._-] segments joined by /, "
    "with no . or .. segment and no leading or trailing /"
)


def set_initiative_folder(ports: ProjectPorts, repository_id: UUID, folder: str) -> Repository:
    """Store `folder` on a stored Repository, committing once."""
    repositories = project_use_cases._repos(ports)
    stored = project_use_cases._require_repository(repositories, repository_id)
    if not is_valid_folder(folder):
        raise Invalid(FOLDER_RULE)
    updated = stored.model_copy(
        update={"initiative_folder": folder, "updated_at": ports.clock.now()}
    )
    repositories.update(updated)
    ports.uow.commit()
    return updated
