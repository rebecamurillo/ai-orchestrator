"""`/api/v1/runs/{run_id}/detail` (SPEC CAP-12, FR-22, FR-23, FR-28): the full Run read model.

Its own module, not a fourth route on `api/routers/run.py`: that module's own frozen test
(`tests/unit/test_run_router.py::test_the_router_declares_exactly_the_three_operations`)
pins it to exactly `POST /runs`, `GET /runs`, `GET /runs/{run_id}`, and a second frozen test
in the same file (`test_get_reads_the_run_just_created`) asserts `GET /runs/{run_id}`'s body
is byte-for-byte `POST /runs`'s embedded `run` — so the fuller shape this story's brief asks
for at "`GET /runs/{id}`" cannot land on that literal route without breaking either. Per the
project's hard rule 1 (frozen tests bind), the full model is served at this sibling path
instead — see the story's own Design Notes for the full account. `GET /runs/{run_id}` keeps
answering the minimal `RunSummaryOut` it always has.
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
from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.run_views import RunDetailOut
from orchestrator.application.use_cases.run_views import RunViewPorts
from orchestrator.application.use_cases.run_views import run_detail as build_detail

router = APIRouter(tags=["runs"])

Ports = Annotated[RunViewPorts, Depends(run_view_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS = {
    404: _refusal("No Run has that id."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`run_id` does not parse as a UUID."),
}


@router.get(
    "/runs/{run_id}/detail",
    response_model=RunDetailOut,
    summary="Read one Run's full detail",
    responses=REFUSALS,
)
def detail(run_id: UUID, ports: Ports) -> RunDetailOut:
    """Everything the Run detail screen shows, from one read (SPEC CAP-12 "one per screen")."""
    return RunDetailOut.of(build_detail(ports, run_id))
