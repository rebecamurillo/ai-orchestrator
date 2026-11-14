"""The analyses behind a Run's shown result version (epic 5 story 5).

Its own router: `run_analysis.py` holds the one SARIF route a test pins.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_metrics import run_analyses_ports
from orchestrator.api.schemas.run_analyses import RunAnalysesOut
from orchestrator.application.use_cases.run_analyses import RunAnalysesPorts, run_analyses

router = APIRouter(tags=["metrics"])

ListPorts = Annotated[RunAnalysesPorts, Depends(run_analyses_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


@router.get(
    "/runs/{run_id}/analysis",
    summary="The analyses behind a Run's shown result version",
    responses={
        404: _refusal("No such Run, or no such result version of it."),
        HTTP_UNPROCESSABLE_CONTENT: _refusal("A path or query value is not valid."),
    },
)
def list_run_analyses(
    run_id: UUID, ports: ListPorts, v: Annotated[int | None, Query(ge=1)] = None
) -> RunAnalysesOut:
    return RunAnalysesOut.of(run_analyses(ports, run_id, v))
