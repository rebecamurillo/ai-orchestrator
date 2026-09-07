"""`POST /api/v1/runs`, `GET /api/v1/runs`, `GET /api/v1/runs/{run_id}` (SPEC CAP-4).

A router of its own, not a growth of `api/routers/runs.py`: that module's own frozen test
(`tests/unit/test_runs_router.py::test_the_router_declares_exactly_the_two_operations`)
pins it to exactly `POST`/`GET /runs/preflight`, the way 3.x already split `templates.py`,
`graph.py` and `graph_text.py` across three routers sharing one prefix rather than growing
any one of them past what its own frozen test names. `main.py` mounts this module beside
`runs.router`, under the same bearer dependency, and — this is the part that is load-bearing
rather than cosmetic — *after* it: `GET /runs/{run_id}` and `GET /runs/preflight` are the
same shape to Starlette's router, which matches registration order, and `templates.router`
already carries the same lesson for `/templates/{name}/{version}` after `/templates/{name}/
versions` and `/templates/{name}/validate`. Mounted the other way round, a request for
`/runs/preflight` would parse `"preflight"` as `run_id` and 422 instead of ever reaching the
pre-flight handler — exactly the failure 3.x's own `graph_text.py` docstring records for
`templates.router`. `tests/unit/test_run_router.py` pins the order with a real request, so a
future reshuffle fails loudly.

`GET /runs` exists for the same reason `GET /runs/preflight` does: `test_bearer_auth.py`
indexes `document["paths"][path]["get"]` for every published path, so a `POST`-only `/runs`
would break that frozen sweep. With no `view` query parameter it answers `RunRepository.
list()` (4.1) as `Page[RunSummaryOut]` — the same minimal read model `GET /runs/{run_id}`
renders, listed rather than pointed at. `?view=board` (4.12, SPEC CAP-12) answers the Board
instead, on this same route rather than a new one — the query string is the only thing that
differs, and `test_run_router.py`'s frozen route-count test only pins methods and paths, so
this stays exactly the three operations it always was. The full `GET /runs/{id}` read model
does *not* land here: see `api/routers/run_detail.py`'s own docstring for why.
"""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import create_run_ports, run_read_ports
from orchestrator.api.schemas.common import Page
from orchestrator.api.schemas.run_views import BoardOut
from orchestrator.api.schemas.runs import CreateRunOut, RunIn, RunSummaryOut, plan_error_problems
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    RunReadPorts,
    create_run,
    get_run,
    park_row_kind_of,
)
from orchestrator.application.use_cases.run_views import board_view
from orchestrator.infrastructure.clock import SystemClock

router = APIRouter(tags=["runs"])

CreatePorts = Annotated[CreateRunPorts, Depends(create_run_ports)]
ReadPorts = Annotated[RunReadPorts, Depends(run_read_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND_RESPONSE = _refusal("No Run has that id.")
CONFLICT_RESPONSE = _refusal("Pre-flight failed at least one line; `detail` names them.")
INVALID_PLAN_RESPONSE = _refusal("The Template tree could not be planned; see `errors[]`.")

CREATE_REFUSALS = {
    409: CONFLICT_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: INVALID_PLAN_RESPONSE,
    404: NOT_FOUND_RESPONSE,
}
BAD_ID_RESPONSE = _refusal("`run_id` does not parse as a UUID.")
# Declared for the same reason `api/routers/templates.py`'s `READ_REFUSALS` declares it on
# `GET /templates/{name}/{version}`: undeclared, FastAPI publishes its own
# `HTTPValidationError` schema for the path-parameter 422 instead of this API's
# `ProblemDetail` — `test_projects_router.py`'s repo-wide sweep checks the whole document.
READ_REFUSALS = {404: NOT_FOUND_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: BAD_ID_RESPONSE}
# `view`/`project_id` (4.12) are the first query parameters this route has ever taken, so
# they are the first thing that can make it answer a 422 — declared for the same reason
# `READ_REFUSALS` is, just above.
BAD_QUERY_RESPONSE = _refusal("`view` or `project_id` does not match the shape below.")
LIST_REFUSALS = {HTTP_UNPROCESSABLE_CONTENT: BAD_QUERY_RESPONSE}


@router.post(
    "/runs",
    response_model=CreateRunOut,
    status_code=201,
    summary="Create and enqueue a Run",
    responses=CREATE_REFUSALS,
)
def create(payload: RunIn, ports: CreatePorts) -> CreateRunOut:
    """Re-runs pre-flight; a `fail` line is 409, an unbuildable plan is 422 (AD-7)."""
    try:
        result = create_run(ports, payload.as_request())
    except PlanError as error:
        raise Problem(
            status=HTTP_UNPROCESSABLE_CONTENT,
            title="invalid plan",
            detail=str(error),
            errors=plan_error_problems(error),
        ) from error
    return CreateRunOut.of(result)


@router.get(
    "/runs",
    response_model=Page[RunSummaryOut] | BoardOut,
    summary="List every Run, or read the Board (`?view=board`)",
    responses=LIST_REFUSALS,
)
def list_runs(
    ports: ReadPorts,
    view: Literal["board"] | None = None,
    project_id: UUID | None = None,
) -> Page[RunSummaryOut] | BoardOut:
    """`?view=board` answers the Board (SPEC CAP-12); otherwise every stored Run, newest
    first, the minimal summary."""
    if view == "board":
        return BoardOut.of(board_view(ports, project_id=project_id, now=SystemClock().now()))
    items = [RunSummaryOut.of(run) for run in ports.runs.list(project_id=project_id)]
    return Page[RunSummaryOut](items=items, next_cursor=None)


# Registered last, and mounted after `runs.router` in `main.py`: see the module docstring
# for why `/runs/{run_id}` must never be checked before the literal `/runs/preflight`.
@router.get(
    "/runs/{run_id}",
    response_model=RunSummaryOut,
    summary="Read one Run",
    responses=READ_REFUSALS,
)
def get(run_id: UUID, ports: ReadPorts) -> RunSummaryOut:
    """The minimal Run read model; `GET /runs/{run_id}` gains the full one in 4.12."""
    run = get_run(ports, run_id)
    return RunSummaryOut.of(run, park_row_kind=park_row_kind_of(ports, run))
