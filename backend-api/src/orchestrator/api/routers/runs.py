"""`/api/v1/runs/preflight` — every FR-8 check line, before a Run is created (SPEC CAP-3).

`test_bearer_auth.py` indexes `paths[path]["get"]` for every published `/api/v1` path
(`api/routers/clone_check.py` names the precedent), so `GET /runs/preflight` ships beside
the `POST`: it answers the same computation over an entirely empty request — every field
absent, which the brief's own rule already makes every line `skip` and `start_allowed:
false` (the AC for a request missing only `repository_id`). It is not a placeholder: it is
the pre-flight the New-workflow screen would show before the Operator has touched the form.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers import preflight_ports
from orchestrator.api.schemas.preflight import PreflightIn, PreflightOut
from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.use_cases.preflight import PreflightPorts, run_preflight

router = APIRouter(tags=["runs"])

Ports = Annotated[PreflightPorts, Depends(preflight_ports)]

# Declared so FastAPI never publishes its own `HTTPValidationError` shape for the 422 a
# malformed body produces — `test_projects_router.py`'s repo-wide sweep checks the whole
# document for that schema, not only this router's own paths.
POST_REFUSALS = {
    HTTP_UNPROCESSABLE_CONTENT: {
        "model": ProblemDetail,
        "description": "The posted body does not match the shape below.",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }
}


@router.post(
    "/runs/preflight",
    response_model=PreflightOut,
    summary="Pre-flight a Run",
    responses=POST_REFUSALS,
)
def preflight(payload: PreflightIn, ports: Ports) -> PreflightOut:
    """Every FR-8 line, `start_allowed`, the queue note, and the rows the plan would persist."""
    return PreflightOut.of(run_preflight(ports, payload.as_request()))


@router.get("/runs/preflight", response_model=PreflightOut, summary="Pre-flight an empty request")
def preflight_empty(ports: Ports) -> PreflightOut:
    """The same computation over an entirely empty request — every line `skip`."""
    return PreflightOut.of(run_preflight(ports, PreflightRequest()))
