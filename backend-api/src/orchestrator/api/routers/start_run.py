"""`POST /api/v1/runs/{run_id}/start` (story 5-3): start a saved Run.

A saved Run has `status="queued"` and `engine_ref={}`. This endpoint re-probes pre-flight
and starts it if all checks pass — 409 if already enqueued, not queued, or pre-flight fails.

A router of its own, for the reason `signals.py` is its own: the signals router is anchored
at exactly two routes (`test_signals_router.py`), so a new operation on a related resource
gets a new module rather than growing an anchored one.
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
from orchestrator.api.providers import start_run_ports
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.application.use_cases.start_run import StartRunPorts, start_saved_run

router = APIRouter(tags=["runs"])

StartPorts = Annotated[StartRunPorts, Depends(start_run_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


POST_REFUSALS = {
    404: _refusal("No Run has that id."),
    409: _refusal("The Run is not in saved state, or pre-flight refuses to start it."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("`run_id` does not parse as a UUID."),
}


@router.post(
    "/runs/{run_id}/start",
    response_model=RunSummaryOut,
    summary="Start a saved Run (story 5-3)",
    responses=POST_REFUSALS,
)
def post_start(run_id: UUID, ports: StartPorts) -> RunSummaryOut:
    """Re-probe pre-flight and start a saved (not-enqueued) Run.

    409 if the Run's `engine_ref` is non-empty (already enqueued), if its status is not
    `queued`, or if the re-probed pre-flight returns `start_allowed=False`.
    """
    with ports.writers.uow:
        outcome = start_saved_run(ports, run_id)
    return RunSummaryOut.of(outcome.run)
