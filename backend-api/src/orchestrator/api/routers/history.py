"""`GET /api/v1/steps` (SPEC CAP-5, FR-25 history): every execution of every step, paged.

A router of its own, on a path of its own, for the reason `api/routers/queue.py` and
`api/routers/run_files.py` each give for theirs: `tests/unit/test_runs_router.py` pins
`api/routers/runs.py` at exactly two operations, and each of the other `/runs` modules
carries its own frozen route-count assertion, so a new route is a new module rather than a
third operation on a frozen one. Mounted through `main.py`'s `_mount` helper like every
router but the two `test_graph_text_router.py` reads by AST.

The resource is `/steps` rather than `/runs/steps`: a row of this table belongs to an
attempt, not to any one Run, and the whole point of the read is that it crosses Runs.
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
from orchestrator.api.providers import history_ports
from orchestrator.api.schemas.history import HistoryPageOut
from orchestrator.application.use_cases.history import (
    DEFAULT_LIMIT,
    STATUS_FILTERS,
    HistoryFilters,
    HistoryPorts,
    list_history,
)

router = APIRouter(tags=["history"])

Ports = Annotated[HistoryPorts, Depends(history_ports)]

#: The largest page this endpoint will build. Bounded at the edge rather than clamped
#: silently: a caller asking for ten thousand rows has misunderstood the cursor, and a
#: refusal naming the bound says so where a quietly truncated page would not.
MAX_LIMIT = 200

REFUSALS = {
    HTTP_UNPROCESSABLE_CONTENT: {
        "model": ProblemDetail,
        "description": (
            "`status` is not one of the tokens this endpoint offers, `cursor` is not one it "
            "issued, or `limit` is outside its bounds."
        ),
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }
}

STATUS_DESCRIPTION = f"One of {' '.join(sorted(STATUS_FILTERS))}. Omitted means every status."


def history_filters(
    project_id: Annotated[UUID | None, Query()] = None,
    status: Annotated[str | None, Query(description=STATUS_DESCRIPTION)] = None,
    harness: Annotated[str | None, Query()] = None,
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
) -> HistoryFilters:
    """The five query parameters as the one bundle the use case takes.

    A dependency rather than five parameters on the handler: the bundle already exists
    (`application/use_cases/history.py::HistoryFilters`, which exists because six arguments
    is one more than ruff's `PLR0913` allows), and declaring it here keeps the same five
    names, defaults and bounds in the generated contract that spelling them on the handler
    would (AD-3 — the browser's types come from this).
    """
    return HistoryFilters(
        project_id=project_id, status=status, harness=harness, cursor=cursor, limit=limit
    )


Filters = Annotated[HistoryFilters, Depends(history_filters)]


@router.get(
    "/steps",
    response_model=HistoryPageOut,
    summary="Read the history: one row per attempt, newest first",
    responses=REFUSALS,
)
def read_history(ports: Ports, filters: Filters) -> HistoryPageOut:
    """One page of executed attempts. Writes nothing; derives no status (AD-8)."""
    return HistoryPageOut.of(list_history(ports, filters))
