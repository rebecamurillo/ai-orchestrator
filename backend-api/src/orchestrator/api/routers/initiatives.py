"""`/api/v1/initiatives` — pre-flight, dispatch, and the cross-repo DAG (AD-12, AD-13).

Three operations, one per row of the spine's routes table: `POST /initiatives/preflight`
(pure, no writes), `POST /initiatives` (the dispatch), `GET /initiatives/{slug}` (the read
model). `POST /initiatives/{slug}/signals` is the fourth and belongs to a later story.

Thin, like every router here: parse the body, call one use case, map the result.
`Conflict` → 409 and `NotFound` → 404 come from `api/errors.py::DOMAIN_STATUS`, so neither
is caught here — the dispatch's own refusal sentence is what the Operator reads.

`/initiatives/preflight` is registered before `/initiatives/{slug}`, which is load-bearing
for the same reason `run.py` registers `GET /runs/preflight` before `GET /runs/{run_id}`:
Starlette matches in registration order, and the literal path has to be checked first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import status as http_status

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_initiatives import (
    dispatch_ports,
    initiative_preflight_ports,
    initiative_read_ports,
)
from orchestrator.api.schemas.initiatives import (
    DispatchOut,
    InitiativeIn,
    InitiativeOut,
    InitiativePreflightOut,
)
from orchestrator.application.use_cases.dispatch_initiative import (
    DispatchPorts,
    dispatch_initiative,
    preflight_initiative,
)
from orchestrator.application.use_cases.initiative_view import (
    InitiativeReadPorts,
    get_initiative,
)
from orchestrator.application.use_cases.preflight import PreflightPorts

router = APIRouter(tags=["initiatives"])


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


VALIDATION_RESPONSE = _refusal("The posted body does not match the shape below.")
NOT_FOUND_RESPONSE = _refusal("No Project, Repository or initiative of that name.")
CONFLICT_RESPONSE = _refusal("A pre-flight line refuses this initiative; the detail names it.")

PREFLIGHT_REFUSALS = {404: NOT_FOUND_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}
DISPATCH_REFUSALS = {
    404: NOT_FOUND_RESPONSE,
    409: CONFLICT_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE,
}
READ_REFUSALS = {404: NOT_FOUND_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: VALIDATION_RESPONSE}

ReadPorts = Annotated[PreflightPorts, Depends(initiative_preflight_ports)]
WritePorts = Annotated[DispatchPorts, Depends(dispatch_ports)]
ViewPorts = Annotated[InitiativeReadPorts, Depends(initiative_read_ports)]


@router.post(
    "/initiatives/preflight",
    response_model=InitiativePreflightOut,
    summary="Pre-flight a multi-repository initiative",
    responses=PREFLIGHT_REFUSALS,
)
def preflight(payload: InitiativeIn, ports: ReadPorts) -> InitiativePreflightOut:
    """Every line the dispatch would refuse on, the repo table, and the DAG it would build."""
    return InitiativePreflightOut.of(preflight_initiative(ports, payload.as_request()))


@router.post(
    "/initiatives",
    response_model=DispatchOut,
    status_code=http_status.HTTP_201_CREATED,
    summary="Dispatch a multi-repository initiative",
    responses=DISPATCH_REFUSALS,
)
def dispatch(payload: InitiativeIn, ports: WritePorts) -> DispatchOut:
    """Create every member Run saved, in topological order, then enqueue wave 0 (AD-12)."""
    return DispatchOut.of(dispatch_initiative(ports, payload.as_request()))


@router.get(
    "/initiatives/{slug}",
    response_model=InitiativeOut,
    summary="Read one initiative's cross-repository DAG",
    responses=READ_REFUSALS,
)
def read(slug: str, ports: ViewPorts) -> InitiativeOut:
    """The member Runs and the repositories they work in — one object, not a list."""
    return InitiativeOut.of(get_initiative(ports, slug))
