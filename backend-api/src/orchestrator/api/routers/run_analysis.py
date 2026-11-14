"""The stored SARIF of a Run's analysis (epic 5 story 4; SPEC CAP-4)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_metrics import analysis_read_ports
from orchestrator.application.use_cases.analysis_sarif import (
    SARIF_MEDIA_TYPE,
    AnalysisReadPorts,
    read_sarif,
)

router = APIRouter(tags=["metrics"])

ReadPorts = Annotated[AnalysisReadPorts, Depends(analysis_read_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


@router.get(
    "/runs/{run_id}/analysis/{analysis_id}/sarif/{tool}",
    summary="The SARIF report one tool wrote for one analysis of a Run",
    response_class=Response,
    responses={
        200: {
            "description": "The stored SARIF, decompressed.",
            "content": {SARIF_MEDIA_TYPE: {"schema": {"type": "object"}}},
        },
        404: _refusal("No such analysis of the Run, or the tool wrote no SARIF for it."),
        HTTP_UNPROCESSABLE_CONTENT: _refusal("A path value is not valid."),
    },
)
def read_analysis_sarif(run_id: UUID, analysis_id: UUID, tool: str, ports: ReadPorts) -> Response:
    body = read_sarif(ports.analyses, ports.uow, run_id, analysis_id, tool)
    return Response(content=body, media_type=SARIF_MEDIA_TYPE)
