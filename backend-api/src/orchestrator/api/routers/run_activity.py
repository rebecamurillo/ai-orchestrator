"""`POST /api/v1/runs/{run_id}/activity` (SM-2, story 8-2): batch-report Operator focus time.

Its own module, not a fourth route on `api/routers/run.py` or a second route on
`api/routers/run_detail.py`: the frozen route-count tests for both files prevent adding a
route there. The same precedent `run_detail.py` set (see its own module docstring) applies.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers import activity_ports
from orchestrator.application.use_cases.activity import ActivityPorts, record_activity
from orchestrator.domain.errors import NotFound

router = APIRouter(tags=["runs"])

Ports = Annotated[ActivityPorts, Depends(activity_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS = {
    404: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "`run_id` does not parse as a UUID, or `focused_seconds` is outside [1, 3600]."
    ),
}


class ActivityIn(BaseModel):
    focused_seconds: int = Field(ge=1, le=3600)


class ActivityOut(BaseModel):
    active_seconds: int


@router.get(
    "/runs/{run_id}/activity",
    response_model=ActivityOut,
    summary="Read accumulated active seconds for a Run",
    responses=REFUSALS,
)
def read_activity(run_id: UUID, ports: Ports) -> ActivityOut:
    """Return `run.active_seconds` as accumulated so far (readable at any status)."""
    run = ports.runs.get(run_id)
    if run is None:
        raise NotFound(f"no run with id {run_id}")
    return ActivityOut(active_seconds=run.active_seconds)


@router.post(
    "/runs/{run_id}/activity",
    response_model=ActivityOut,
    summary="Report Operator focus time for a Run",
    responses=REFUSALS,
)
def report_activity(run_id: UUID, body: ActivityIn, ports: Ports) -> ActivityOut:
    """Increment `run.active_seconds` by `focused_seconds` and return the new total."""
    new_total = record_activity(ports, run_id, body.focused_seconds)
    return ActivityOut(active_seconds=new_total)
