"""`POST /api/v1/repositories/{id}/init` (SPEC CAP-10, FR-30, AD-16, AD-12): the Repository
row's own *Initialise repository* action.

A router of its own rather than a growth of `api/routers/repositories.py` or `.../
clone_check.py`, for the reason every sibling split in this codebase gives: both of those
carry their own frozen route-count or path-set test
(`test_repositories_router.py::test_the_router_declares_four_operations_and_repeats_no_dependency`),
so a fifth operation on either path gets a new module instead (4.4's `run.py` beside
`runs.py` is the first precedent; 4.9's `signals.py` beside `run.py` is the most recent one).

`GET /repositories/{id}/init` exists for the reason every sibling `GET` on a `POST`-only path
in this codebase does: `test_bearer_auth.py` indexes `document["paths"][path]["get"]` for
every published path. It answers the same question `GET /repositories/{id}` does — this is
the same move 4.9's `GET /runs/{id}/signals` makes for `GET /runs/{id}`.

The action itself is `create_run` (4.4) composed by `use_cases.repositories.init_repository`
(4.10): this module is only the HTTP — which status a create answers with, and how a
`CreateRunResult` becomes the same `CreateRunOut` `POST /runs` already answers with.
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
from orchestrator.api.providers import create_run_ports, project_ports
from orchestrator.api.schemas.projects import RepositoryOut
from orchestrator.api.schemas.runs import CreateRunOut, RepoInitIn
from orchestrator.application.use_cases import projects as project_use_cases
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.application.use_cases.repositories import init_repository

router = APIRouter(tags=["repositories"])

#: One path, two operations, named once so neither can drift from the other.
INIT_PATH = "/repositories/{repository_id}/init"


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND_RESPONSE = _refusal("No Repository has that id.")
CONFLICT_RESPONSE = _refusal(
    "The clone check has failed, or a repo-init Run is already running on this Repository."
)
VALIDATION_RESPONSE = _refusal("The request broke a rule; `errors[]` names it and the reason.")

POST_REFUSALS = {
    404: NOT_FOUND_RESPONSE,
    409: CONFLICT_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE,
}
GET_REFUSALS = {404: NOT_FOUND_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}

CreatePorts = Annotated[CreateRunPorts, Depends(create_run_ports)]
ReadPorts = Annotated[ProjectPorts, Depends(project_ports)]


@router.post(
    INIT_PATH,
    response_model=CreateRunOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Initialise this Repository for the method",
    responses=POST_REFUSALS,
)
def init(repository_id: UUID, ports: CreatePorts, body: RepoInitIn | None = None) -> CreateRunOut:
    """Start a `repo-init@1` Run on `repository.default_branch`; the optional body names
    the harness its `agent` rows dispatch, else `create_run`'s own default stands."""
    harness = body.harness if body is not None else None
    return CreateRunOut.of(init_repository(ports, repository_id, harness))


@router.get(
    INIT_PATH,
    response_model=RepositoryOut,
    summary="Read the Repository this path initialises",
    responses=GET_REFUSALS,
)
def get_init(repository_id: UUID, ports: ReadPorts) -> RepositoryOut:
    """The same read `GET /repositories/{id}` gives, published under this path too (4.10)."""
    return RepositoryOut.of(project_use_cases.get_repository(ports, repository_id))
