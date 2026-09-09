"""`GET /api/v1/runs/{run_id}/files` (story 6-2, SPEC CAP-2, FR-19): a read-only look at one
file inside a Run's own spec folder — what the spec-checkpoint body shows inline.

A router of its own, on the same `/runs` prefix `runs.py`/`run.py`/`run_detail.py`/
`signals.py` already share, for the same reason each of those already is: `runs.py` carries
its own frozen route-count test (`tests/unit/test_runs_router.py::
test_the_router_declares_exactly_the_two_operations`, pinned to `GET`/`POST /runs/
preflight`), so a third operation on that resource gets a new module rather than growing it
— exactly what `run_detail.py`'s and `signals.py`'s own docstrings already explain for
their own frozen siblings. The brief's own implementation note ("in `api/routers/
runs.py`") is an implementation note, not a binding rule; this is the honest alternative
that keeps the frozen test true. Mounted after `signals.router` in `main.py`.
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
from orchestrator.api.providers import run_files_ports
from orchestrator.api.schemas.run_files import RunFileOut
from orchestrator.application.use_cases.run_files import RunFilesPorts, read_run_file

router = APIRouter(tags=["runs"])

Ports = Annotated[RunFilesPorts, Depends(run_files_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


GET_REFUSALS = {
    403: _refusal("The path is well formed but outside the Run's own spec folder."),
    404: _refusal("No Run has that id, or no file is there."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The path escapes the workspace (`..`, or absolute)."),
}


@router.get(
    "/runs/{run_id}/files",
    response_model=RunFileOut,
    summary="Read one file inside a Run's own spec folder",
    responses=GET_REFUSALS,
)
def get_file(run_id: UUID, ports: Ports, path: Annotated[str, Query()]) -> RunFileOut:
    """Read-only (6.3 adds the write): `path` may be a single-segment glob, resolved here —
    see the use case's own docstring for the exact refusal order."""
    return RunFileOut.of(read_run_file(ports, run_id, path))
