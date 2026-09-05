"""`/api/v1` Repository operations — registering the git repositories a Run works in.

Every rule this feature has is somewhere else: the shape rules in
`api/schemas/projects.py`, the business rules in `application/use_cases/projects.py`, the
vocabulary in `domain/entities/repository.py`. What is left here is the HTTP: which status a
create answers with, which envelope the list uses, and how a `Repository` becomes a
`RepositoryOut`.

Two routes are nested under a Project (`add_repository`, `list_repositories`) and two are
addressed by the Repository's own id (`get_repository`, `update_repository`) — the same
split `GET /projects/{id}` and this router's list route make between "under a Project" and
"by its own id". `list_repositories` is what keeps `add_repository`'s path from publishing a
`POST` with no `GET` beside it (`tests/unit/test_bearer_auth.py`).

The bearer dependency is not repeated on any route: `main.py` attaches it to the whole
`/api/v1` prefix (AD-4).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers import project_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.projects import RepositoryCreate, RepositoryOut, RepositoryUpdate
from orchestrator.application.use_cases import projects as use_cases
from orchestrator.application.use_cases.projects import ProjectPorts

router = APIRouter(tags=["repositories"])

HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


#: The 422 this API actually sends, declared so FastAPI does not publish its own instead.
VALIDATION_RESPONSE = _refusal("The request broke a rule; `errors[]` names it and the reason.")
NOT_FOUND_RESPONSE = _refusal("No Project or Repository has that id.")
CONFLICT_RESPONSE = _refusal("Another Repository in this Project already holds that url.")

VALIDATION = {HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}
READ_REFUSALS = {**VALIDATION, HTTP_NOT_FOUND: NOT_FOUND_RESPONSE}
CREATE_REFUSALS = {**READ_REFUSALS, HTTP_CONFLICT: CONFLICT_RESPONSE}
UPDATE_REFUSALS = {**READ_REFUSALS, HTTP_CONFLICT: CONFLICT_RESPONSE}

Ports = Annotated[ProjectPorts, Depends(project_ports)]


@router.post(
    "/projects/{project_id}/repositories",
    response_model=RepositoryOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Register a Repository under a Project",
    responses=CREATE_REFUSALS,
)
def add_repository(project_id: UUID, payload: RepositoryCreate, ports: Ports) -> RepositoryOut:
    """Store a Repository. Its `clone_check` starts `pending` until a check is run."""
    return RepositoryOut.of(use_cases.add_repository(ports, project_id, payload.as_draft()))


@router.get(
    "/projects/{project_id}/repositories",
    response_model=Page[RepositoryOut],
    summary="List a Project's Repositories",
    responses=READ_REFUSALS,
)
def list_repositories(project_id: UUID, ports: Ports) -> Page[RepositoryOut]:
    """Every Repository stored under this Project, in the order they were created."""
    items = [
        RepositoryOut.of(repository)
        for repository in use_cases.list_repositories_by_project(ports, project_id)
    ]
    return Page[RepositoryOut](items=items, next_cursor=None)


@router.get(
    "/repositories/{repository_id}",
    response_model=RepositoryOut,
    summary="Read one Repository",
    responses=READ_REFUSALS,
)
def get_repository(repository_id: UUID, ports: Ports) -> RepositoryOut:
    """One stored Repository. An unknown id is a 404 problem document."""
    return RepositoryOut.of(use_cases.get_repository(ports, repository_id))


@router.put(
    "/repositories/{repository_id}",
    response_model=RepositoryOut,
    summary="Update a Repository",
    responses=UPDATE_REFUSALS,
)
def update_repository(
    repository_id: UUID, payload: RepositoryUpdate, ports: Ports
) -> RepositoryOut:
    """Replace a Repository's editable fields. Its `clone_check` and slug are untouched."""
    return RepositoryOut.of(use_cases.update_repository(ports, repository_id, payload.as_draft()))
