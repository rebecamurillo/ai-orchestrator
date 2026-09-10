"""`GET /api/v1/projects/{id}/trajectories.jsonl` (SPEC CAP-6, AD-19, FR-32 export): every
stored trajectory of a Project, newest first, as JSON lines.

A router of its own, on a path of its own, for the reason `api/routers/history.py` gives for
its own: `tests/unit/test_projects_router.py` pins `api/routers/projects.py` at exactly four
operations, so a new route is a new module rather than a fifth operation on a frozen one.

The body is `application/x-ndjson`, not `application/json` — one line is one Trajectory
(`api/schemas/trajectories.py::TrajectoryLineOut`), not a list inside `{items, next_cursor}`
(the one envelope every other list in this API uses). There is therefore no `response_model`:
FastAPI would try to render the `StreamingResponse` object itself as the body a pydantic model
describes, which it is not.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    ProblemDetail,
)
from orchestrator.api.providers_trajectories import trajectory_export_ports
from orchestrator.api.schemas.trajectories import TrajectoryLineOut
from orchestrator.application.use_cases.trajectory_export import (
    TrajectoryExportPorts,
    prepare_export,
)
from orchestrator.domain.entities.trajectory import Trajectory

router = APIRouter(tags=["trajectories"])

HTTP_NOT_FOUND = 404
NDJSON_MEDIA_TYPE = "application/x-ndjson"

#: How many lines the streamed response writes per chunk — the brief's own page size. The
#: whole list is already in memory (`prepare_export`'s own docstring: the port has no paged
#: query), so this paces the *bytes the browser receives*, not the database read.
PAGE_SIZE = 100

NOT_FOUND_RESPONSE = {
    "model": ProblemDetail,
    "description": "No Project has that id.",
    "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
}
REFUSALS = {
    HTTP_UNPROCESSABLE_CONTENT: {
        "model": ProblemDetail,
        "description": "`project_id` is not a UUID.",
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    },
    HTTP_NOT_FOUND: NOT_FOUND_RESPONSE,
}

Ports = Annotated[TrajectoryExportPorts, Depends(trajectory_export_ports)]


def _lines(trajectories: list[Trajectory]) -> Iterator[str]:
    """Every trajectory as one ndjson line, written in chunks of `PAGE_SIZE`."""
    for start in range(0, len(trajectories), PAGE_SIZE):
        page = trajectories[start : start + PAGE_SIZE]
        yield "".join(f"{TrajectoryLineOut.of(row).model_dump_json()}\n" for row in page)


@router.get(
    "/projects/{project_id}/trajectories.jsonl",
    summary="Export a Project's trajectories as JSON lines, newest first",
    responses=REFUSALS,
)
def export_trajectories(project_id: UUID, ports: Ports) -> StreamingResponse:
    """The stream `Export trajectories` (UX-DR12) downloads. Writes nothing, derives no
    status (AD-8) — every field is read straight off the stored `Trajectory` rows (5.9)."""
    filename, trajectories = prepare_export(ports, project_id)
    return StreamingResponse(
        _lines(trajectories),
        media_type=NDJSON_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
