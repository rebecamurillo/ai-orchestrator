"""`POST /api/v1/harnesses/{name}/readiness` (SPEC CAP-8).

A router of its own, not a growth of `api/routers/harnesses.py`: that module's own frozen
test (`tests/unit/test_harnesses_router.py::
test_the_router_declares_exactly_one_route_with_no_dependency_of_its_own`) pins it to
exactly `GET /harnesses`, the same reason `api/routers/run.py`'s own docstring gives for
splitting `POST /runs` out of `runs.py`.

`GET /harnesses/{name}/readiness` reads the one harness's current line — the same
`HarnessOut` shape `GET /harnesses` renders, just addressed by name rather than listed —
which exists for the same reason `runs.py`'s own `GET /runs/preflight` does: `test_bearer_
auth.py::test_the_contract_declares_the_401_and_its_media_type` indexes `paths[path]["get"]`
for every published `/api/v1` path, so a `POST`-only path would break that frozen sweep.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import harness_ports, readiness_ports
from orchestrator.api.schemas.harnesses import HarnessOut
from orchestrator.api.schemas.runs import CreateRunOut
from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.harness_readiness import HarnessReadinessPorts, start
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.domain.entities.harness import HARNESS_NAME_PATTERN
from orchestrator.domain.errors import NotFound

router = APIRouter(tags=["harnesses"])

StartPorts = Annotated[HarnessReadinessPorts, Depends(readiness_ports)]
ReadPorts = Annotated[HarnessPorts, Depends(harness_ports)]

#: The shape both operations take the name in, and the shape `BAD_NAME_RESPONSE` below has
#: always said they publish. Declared rather than checked in the handlers because `GET`
#: compares the name to `harness.name` in Postgres, which cannot hold a NUL byte: without it
#: such a name reached psycopg as a `DataError` and answered 500 (schemathesis, 2026-09-18).
#: Not `HARNESS_NAMES` — `start` checks membership itself and answers 404, and `GET` serves
#: the `fake` harness `ORCH_TEST_MODE` seeds, whose name that tuple does not list.
Name = Annotated[str, Path(pattern=HARNESS_NAME_PATTERN)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


CONFLICT_RESPONSE = _refusal(
    "A non-terminal readiness Run for this harness already exists, or this instance's "
    "READINESS_MODELS binds no model for it."
)
NOT_FOUND_RESPONSE = _refusal("The readiness Project or Repository is not seeded.")
NO_SUCH_HARNESS_RESPONSE = _refusal("No harness has that name.")
# undeclared, FastAPI would publish its own `HTTPValidationError` schema for the path
# parameter's 422 — `test_projects_router.py`'s repo-wide sweep checks the whole document
# (`api/routers/run.py`'s own `READ_REFUSALS` is the precedent).
BAD_NAME_RESPONSE = _refusal("`name` does not match the shape below.")

START_REFUSALS = {
    409: CONFLICT_RESPONSE,
    404: NOT_FOUND_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: BAD_NAME_RESPONSE,
}
READ_REFUSALS = {404: NO_SUCH_HARNESS_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: BAD_NAME_RESPONSE}


@router.post(
    "/harnesses/{name}/readiness",
    response_model=CreateRunOut,
    status_code=201,
    summary="Dispatch a readiness Run for one harness",
    responses=START_REFUSALS,
)
def start_readiness(name: Name, ports: StartPorts) -> CreateRunOut:
    """Dispatch a Run of the configured readiness Template (`READINESS_TEMPLATE`, latest
    stored version) against the fixture Repository, `skip_harness_check` bypassing
    the disabled-harness pre-flight line (AD-10) so a harness never yet enabled can still
    run the Run that would enable it."""
    try:
        result = start(ports, name)
    except PlanError as error:
        raise Problem(
            status=HTTP_UNPROCESSABLE_CONTENT,
            title="invalid plan",
            detail=str(error),
        ) from error
    return CreateRunOut.of(result)


@router.get(
    "/harnesses/{name}/readiness",
    response_model=HarnessOut,
    summary="Read one harness's current readiness",
    responses=READ_REFUSALS,
)
def get_readiness(name: Name, ports: ReadPorts) -> HarnessOut:
    """The same row `GET /harnesses` lists, addressed by name."""
    harness = ports.harnesses.get(name)
    if harness is None:
        raise NotFound(f"no harness named {name!r}")
    return HarnessOut.of(harness)
