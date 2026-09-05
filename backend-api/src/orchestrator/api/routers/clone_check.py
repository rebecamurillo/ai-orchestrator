"""`/api/v1/repositories/{id}/clone-check` — running one, and reading the last one.

A router of its own rather than two more routes on `api/routers/repositories.py`, for the
reason that module's own contract test states: it declares exactly the four operations that
*register* a Repository, and this pair is about a Repository's state rather than its
registration. `main.py` mounts this one with the same prefix and the same bearer dependency,
so the split is invisible from outside — one path, two operations, one credential (AD-4).

The two differ in exactly one way, and it is the whole reason both exist: the `POST` runs
git and stores what it found; the `GET` reads what was stored and runs nothing. A read that
re-ran the check would put a clone behind every page load. Publishing the `GET` is also what
keeps this path from carrying a `POST` with no `GET` beside it
(`tests/unit/test_bearer_auth.py` indexes every published path's `get`).

A check that failed is a 200 carrying the failure: the request did exactly what it was asked
to, and "this repository cannot be cloned" is the answer, not an error. The refusals here are
about the *request* — an id that names nothing is a 404, an id that is not a UUID is a 422.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.deps import get_settings
from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers import project_ports
from orchestrator.api.schemas.clone_check import CloneCheckResultOut
from orchestrator.application.use_cases import clone_check as use_cases
from orchestrator.application.use_cases import projects as project_use_cases
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.infrastructure.settings import Settings

router = APIRouter(tags=["repositories"])

HTTP_NOT_FOUND = 404

#: One path, two operations. Named once so the `POST` and the `GET` cannot drift apart.
CLONE_CHECK_PATH = "/repositories/{repository_id}/clone-check"


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS = {
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "The request broke a rule; `errors[]` names it and the reason."
    ),
    HTTP_NOT_FOUND: _refusal("No Repository has that id."),
}

Ports = Annotated[ProjectPorts, Depends(project_ports)]
Config = Annotated[Settings, Depends(get_settings)]


@router.post(
    CLONE_CHECK_PATH,
    response_model=CloneCheckResultOut,
    summary="Run this Repository's clone check",
    responses=REFUSALS,
)
def run_clone_check(repository_id: UUID, ports: Ports, settings: Config) -> CloneCheckResultOut:
    """Reach the remote, make or refresh the base clone, and store what happened.

    `WORK_DIR` and `BMAD_VERSION` reach the use case as arguments, because nothing under
    `application/` reads the environment (AD-20).
    """
    checked = use_cases.run_clone_check(
        ports,
        repository_id,
        work_dir=settings.work_dir,
        bmad_version=settings.bmad_version,
    )
    return CloneCheckResultOut.of(checked.clone_check)


@router.get(
    CLONE_CHECK_PATH,
    response_model=CloneCheckResultOut,
    summary="Read this Repository's last clone check",
    responses=REFUSALS,
)
def read_clone_check(repository_id: UUID, ports: Ports) -> CloneCheckResultOut:
    """The stored result, and no git command. `pending` until a check has run."""
    stored = project_use_cases.get_repository(ports, repository_id)
    return CloneCheckResultOut.of(stored.clone_check)
