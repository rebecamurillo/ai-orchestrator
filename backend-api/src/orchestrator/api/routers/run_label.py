"""`PATCH /api/v1/runs/{run_id}`: set or restore a Run's label (story 3; SPEC CAP-3).

A router of its own: `routers/run.py` is pinned to three operations by its frozen test.
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
from orchestrator.api.providers_run_label import run_label_ports
from orchestrator.api.schemas.runs import RunLabelIn, RunSummaryOut
from orchestrator.application.use_cases.create_run import park_row_in
from orchestrator.application.use_cases.run_label import RunLabelPorts, set_run_label

router = APIRouter(tags=["runs"])

LabelPorts = Annotated[RunLabelPorts, Depends(run_label_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


LABEL_REFUSALS = {
    404: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "The label is empty or over 120 characters, or `run_id` is not a UUID."
    ),
}


@router.patch(
    "/runs/{run_id}",
    response_model=RunSummaryOut,
    summary="Set or restore a Run's label",
    responses=LABEL_REFUSALS,
)
def patch_label(run_id: UUID, payload: RunLabelIn, ports: LabelPorts) -> RunSummaryOut:
    """A string of 1-120 characters sets the label; `null` restores the computed default.
    Allowed at every status; never touches the status."""
    run, rows = set_run_label(ports, run_id, payload.label)
    park_row = park_row_in(run, rows)
    return RunSummaryOut.of(
        run,
        park_row_kind=park_row.kind if park_row is not None else None,
        park_row_status=park_row.status if park_row is not None else None,
        rows=rows,
    )
