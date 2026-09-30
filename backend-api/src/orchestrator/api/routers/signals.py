"""`POST /api/v1/runs/{run_id}/signals` (SPEC CAP-9, FR-20, AD-13): one endpoint for every
action on a Run.

A router of its own, on the same `/runs` prefix `runs.py` and `run.py` already share, for
the same reason 4.4's `run.py` is not a growth of `runs.py`: both carry their own frozen
route-count test, so a new operation on the same resource gets a new module rather than
either of theirs. Mounted after `run.router` in `main.py` — `/runs/{run_id}` and `/runs/
{run_id}/signals` are different path shapes to Starlette either way, but the composition
root keeps every `/runs` router in the order this epic's routers were added.

`GET /runs/{run_id}/signals` exists for the reason every sibling `GET` on a `POST`-only path
in this codebase does: `test_bearer_auth.py` indexes `document["paths"][path]["get"]` for
every published path, so a `POST`-only `/runs/{id}/signals` would break that frozen sweep.
It answers the same question `GET /runs/{run_id}` does — the Run, with `admitted_signals` —
through the path the New-workflow screen's own actions live under.
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
from orchestrator.api.providers import run_read_ports, signal_effect_ports
from orchestrator.api.schemas.runs import RunSummaryOut
from orchestrator.api.schemas.signals import SignalIn
from orchestrator.application.use_cases.create_run import (
    RunReadPorts,
    get_run,
    park_row_in,
    run_rows,
)
from orchestrator.application.use_cases.signals import SignalEffectPorts, handle_signal

router = APIRouter(tags=["runs"])

EffectPorts = Annotated[SignalEffectPorts, Depends(signal_effect_ports)]
ReadPorts = Annotated[RunReadPorts, Depends(run_read_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND_RESPONSE = _refusal("No Run has that id.")
CONFLICT_RESPONSE = _refusal(
    "The signal does not apply to this Run's status or park, or is not available yet."
)
BAD_ID_RESPONSE = _refusal("`run_id` does not parse as a UUID.")
POST_REFUSALS = {
    404: NOT_FOUND_RESPONSE,
    409: CONFLICT_RESPONSE,
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The posted body does not match the shape below."),
}
# Declared for the same reason `api/routers/run.py::READ_REFUSALS` declares it: undeclared,
# FastAPI publishes its own `HTTPValidationError` schema for the path-parameter 422 instead
# of this API's `ProblemDetail` — `test_projects_router.py`'s repo-wide sweep checks the
# whole document.
GET_REFUSALS = {404: NOT_FOUND_RESPONSE, HTTP_UNPROCESSABLE_CONTENT: BAD_ID_RESPONSE}


@router.post(
    "/runs/{run_id}/signals",
    response_model=RunSummaryOut,
    summary="Signal a Run: cancel, retry, or continue",
    responses=POST_REFUSALS,
)
def post_signal(run_id: UUID, payload: SignalIn, ports: EffectPorts) -> RunSummaryOut:
    """Validate against AD-13, refuse a kind this epic does not apply yet, then apply it."""
    outcome = handle_signal(ports, run_id, payload.as_signal())
    return RunSummaryOut.of(outcome.run)


@router.get(
    "/runs/{run_id}/signals",
    response_model=RunSummaryOut,
    summary="Read the Run this path signals, and what it currently admits",
    responses=GET_REFUSALS,
)
def get_signals(run_id: UUID, ports: ReadPorts) -> RunSummaryOut:
    """The same read `GET /runs/{run_id}` gives, published under this path too (4.9)."""
    run = get_run(ports, run_id)
    rows = run_rows(ports, run)
    park_row = park_row_in(run, rows)
    return RunSummaryOut.of(
        run,
        park_row_kind=park_row.kind if park_row is not None else None,
        rows=rows,
    )
