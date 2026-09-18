"""`GET /api/v1/harnesses/{name}/probe` (story 2-1).

A router of its own, not a growth of `api/routers/harnesses.py` or `harness_readiness.py`:
`test_harnesses_router.py` pins `harnesses.router` to exactly `GET /harnesses` and zero
other routes (frozen anchor), and every path must expose a `get` operation so that
`test_bearer_auth.py`'s contract sweep (`paths[path]["get"]`) finds a declared 401.

HTTP semantics: 200 for every probe that ran — including probes that found problems
(`ok=False`, `failing_reason` populated) — 404 for unknown harness names, and 500 for
adapter faults (JSON parse failure, script missing, etc.).  The bearer guard is inherited
from the mount in `main.py`; this router declares no dependency of its own.
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
from orchestrator.api.providers import harness_probe_ports
from orchestrator.api.schemas.harnesses import ProbeResultOut
from orchestrator.application.use_cases.harness_probe import HarnessProbePorts, probe

router = APIRouter(tags=["harnesses"])

ProbePorts = Annotated[HarnessProbePorts, Depends(harness_probe_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NO_SUCH_HARNESS_RESPONSE = _refusal("No harness has that name.")
BAD_NAME_RESPONSE = _refusal("`name` does not match the shape below.")

PROBE_REFUSALS = {
    404: NO_SUCH_HARNESS_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: BAD_NAME_RESPONSE,
}


@router.get(
    "/harnesses/{name}/probe",
    response_model=ProbeResultOut,
    summary="Run a readiness probe for one harness",
    responses=PROBE_REFUSALS,
)
def run_probe(name: str, ports: ProbePorts) -> ProbeResultOut:
    """Shell the harness's probe verb and return the result.

    `ok=True` means all checks passed; `ok=False` means the probe ran and found a specific
    problem, named in `failing_reason`.  Both are HTTP 200.  Unknown harness names are 404.
    """
    result = probe(ports, name)
    return ProbeResultOut(
        ok=result.ok,
        failing_reason=result.failing_reason,
        version=result.version,
        models=result.models,
    )
