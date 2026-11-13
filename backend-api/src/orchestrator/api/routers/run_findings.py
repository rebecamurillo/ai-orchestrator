"""The findings opengrep stored for one analysis of a Run (epic 6 story 4)."""

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
from orchestrator.api.providers_metrics import analysis_read_ports
from orchestrator.api.schemas.run_findings import FindingsOut
from orchestrator.application.use_cases.analysis_findings import read_findings
from orchestrator.application.use_cases.analysis_sarif import AnalysisReadPorts

router = APIRouter(tags=["metrics"])

ReadPorts = Annotated[AnalysisReadPorts, Depends(analysis_read_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


@router.get(
    "/runs/{run_id}/analysis/{analysis_id}/findings",
    summary="The possible security and bug findings opengrep listed for one analysis",
    response_model=FindingsOut,
    responses={
        404: _refusal("No such analysis of the Run, or opengrep stored no findings for it."),
        HTTP_UNPROCESSABLE_CONTENT: _refusal("A path value is not valid."),
    },
)
def read_analysis_findings(run_id: UUID, analysis_id: UUID, ports: ReadPorts) -> FindingsOut:
    return FindingsOut.of(
        analysis_id, read_findings(ports.analyses, ports.uow, run_id, analysis_id)
    )
