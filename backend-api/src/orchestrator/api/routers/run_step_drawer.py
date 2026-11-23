"""`GET /api/v1/runs/{run_id}/steps/{seq}/attempts/{n}/drawer`: one step in one read (AD-40).

`n = 0` is the row's latest attempt. Read-only; writes no status (AD-8).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_step_drawer import step_drawer_ports
from orchestrator.api.schemas.run_step_drawer import StepDrawerOut
from orchestrator.application.use_cases.run_step_drawer import StepDrawerPorts, step_drawer

router = APIRouter(tags=["runs"])

Ports = Annotated[StepDrawerPorts, Depends(step_drawer_ports)]
Seq = Annotated[int, Path(ge=0)]
N = Annotated[int, Path(ge=0)]

HTTP_NOT_FOUND = 404


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No such Run, step or attempt."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("A path segment does not parse."),
}


@router.get(
    "/runs/{run_id}/steps/{seq}/attempts/{n}/drawer",
    response_model=StepDrawerOut,
    responses=REFUSALS,
    summary="Read one step's drawer: log state, files read and written, attempts, run order",
)
def get_step_drawer(run_id: UUID, seq: Seq, n: N, ports: Ports) -> StepDrawerOut:
    return StepDrawerOut.of(step_drawer(ports, run_id, seq, n))
