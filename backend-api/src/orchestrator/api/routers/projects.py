"""`/api/v1/projects` — four operations, each one call to one use case.

Every rule this feature has is somewhere else: the shape rules in
`api/schemas/projects.py`, the business rules in `application/use_cases/projects.py`, the
vocabulary in `domain/entities/project.py`. What is left here is the HTTP: which status a
create answers with, which envelope a list uses, and how a `ProjectView` becomes a
`ProjectRead`.

The bearer dependency is not repeated on any route: `main.py` attaches it to the whole
`/api/v1` prefix, so this router cannot forget it (AD-4).

One rule does surface here, and only because it is configuration: a create that omits
`log_prompt_content` takes the instance's `LOG_PROMPT_CONTENT_DEFAULT` (FR-2). The settings
object is the only place that value exists, and a use case may not read the environment. An
update omitting the same field keeps what is stored, so `PUT` reads no setting at all.

Every operation renders `ProjectRead`, which embeds `repositories`: each one calls
`use_cases.embedded_repositories` after its own use case, so the answer is never a stale
snapshot from before the Repository router's last write.

Each operation declares every refusal it can answer, and no other. A route taking a path
parameter or a body would otherwise have FastAPI publish a 422 of its own shape, putting
`HTTPValidationError` in the contract the browser generates from (AD-3) while the server
answers `application/problem+json`; the 404 and the 409 are declared for the opposite
reason — nothing would publish them, and the generated client would have no type for the
two refusals this feature answers most (unknown id, duplicate name).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from orchestrator.api.deps import get_settings
from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers import project_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.projects import ProjectCreate, ProjectRead, ProjectUpdate
from orchestrator.application.use_cases import projects as use_cases
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import ProjectView
from orchestrator.infrastructure.settings import Settings

router = APIRouter(tags=["projects"])

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
NOT_FOUND_RESPONSE = _refusal("No Project has that id.")
CONFLICT_RESPONSE = _refusal("Another Project already holds that name.")

VALIDATION = {HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}
CREATE_REFUSALS = {**VALIDATION, HTTP_CONFLICT: CONFLICT_RESPONSE}
READ_REFUSALS = {**VALIDATION, HTTP_NOT_FOUND: NOT_FOUND_RESPONSE}
UPDATE_REFUSALS = {**READ_REFUSALS, HTTP_CONFLICT: CONFLICT_RESPONSE}

Ports = Annotated[ProjectPorts, Depends(project_ports)]
Config = Annotated[Settings, Depends(get_settings)]


def _read(ports: ProjectPorts, view: ProjectView) -> ProjectRead:
    """`ProjectRead.of`, given the Repositories this Project actually has right now."""
    return ProjectRead.of(view, use_cases.embedded_repositories(ports, view.id))


@router.get(
    "/projects",
    response_model=Page[ProjectRead],
    summary="List every Project",
)
def list_projects(ports: Ports) -> Page[ProjectRead]:
    """Every Project, ordered by name, each with its variables masked and Repositories embedded.

    One page: the whole list is small enough that a cursor would be ceremony. The envelope
    is the same one every list in this API uses, so paging can arrive without a break.
    """
    items = [_read(ports, view) for view in use_cases.list_projects(ports)]
    return Page[ProjectRead](items=items, next_cursor=None)


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=http_status.HTTP_201_CREATED,
    summary="Create a Project",
    responses=CREATE_REFUSALS,
)
def create_project(payload: ProjectCreate, ports: Ports, settings: Config) -> ProjectRead:
    """Store a Project. Every variable value is encrypted before it is written (AD-5)."""
    view = use_cases.create_project(
        ports,
        payload.as_draft(),
        log_prompt_content_default=settings.log_prompt_content_default,
    )
    return _read(ports, view)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Read one Project, with its Repositories",
    responses=READ_REFUSALS,
)
def get_project(project_id: UUID, ports: Ports) -> ProjectRead:
    """One Project, with every variable masked and its Repositories embedded, in creation
    order. An unknown id is a 404 problem document."""
    return _read(ports, use_cases.get_project(ports, project_id))


@router.put(
    "/projects/{project_id}",
    response_model=ProjectRead,
    summary="Update a Project",
    responses=UPDATE_REFUSALS,
)
def update_project(project_id: UUID, payload: ProjectUpdate, ports: Ports) -> ProjectRead:
    """Replace a Project's editable fields, and with them its whole variable set.

    A variable sent without a value keeps the ciphertext already stored, which is how a
    form that was never given the secret can send the set back without losing it. An
    omitted `log_prompt_content` keeps the stored switch for the same reason; no instance
    default is read here, so this route takes no settings. Its Repositories are untouched
    by this route and are re-read, not carried over from before the call.
    """
    return _read(ports, use_cases.update_project(ports, project_id, payload.as_draft()))
