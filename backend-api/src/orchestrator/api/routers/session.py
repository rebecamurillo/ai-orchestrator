"""`GET /api/v1/runs/{run_id}/session` (AD-23): the Operator's senior session on one Run.

Read-only. The session opens and closes through `POST /runs/{id}/signals`
(`session_start`, `session_end`); this answers what the Run detail renders around them.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_session import session_ports
from orchestrator.api.schemas.session import SessionOut
from orchestrator.application.use_cases.session_checks import SessionPorts
from orchestrator.application.use_cases.session_view import session_view

router = APIRouter(tags=["runs"])

Ports = Annotated[SessionPorts, Depends(session_ports)]

HTTP_NOT_FOUND = 404


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`run_id` does not parse as a UUID."),
}


@router.get(
    "/runs/{run_id}/session",
    response_model=SessionOut,
    summary="Read the Operator's senior session on a Run",
    responses=REFUSALS,
)
def get_session(run_id: UUID, ports: Ports) -> SessionOut:
    return SessionOut.of(session_view(ports, run_id))
