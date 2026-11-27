"""`GET /api/v1/runs/{run_id}/files-by-epic` and its `/diff`: a Run's files per epic and Story.

Read-only; writes no status (AD-8).
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
from orchestrator.api.providers_run_files import run_files_by_epic_ports
from orchestrator.api.schemas.run_files_by_epic import RunFilesByEpicOut, StoryDiffOut
from orchestrator.application.use_cases.run_files_by_epic import (
    FilesByEpicPorts,
    files_by_epic,
    story_diff,
)

router = APIRouter(tags=["runs"])

Ports = Annotated[FilesByEpicPorts, Depends(run_files_by_epic_ports)]
HTTP_NOT_FOUND = 404


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


LIST_REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No such Run."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The Run id does not parse."),
}
REFUSALS: dict[int | str, dict[str, object]] = {
    HTTP_NOT_FOUND: _refusal("No such Run, epic, story or changed path."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("A path or query value does not parse."),
}


@router.get(
    "/runs/{run_id}/files-by-epic",
    response_model=RunFilesByEpicOut,
    responses=LIST_REFUSALS,
    summary="Read a Run's spec files and changed paths, grouped by epic and Story",
)
def get_files_by_epic(run_id: UUID, ports: Ports) -> RunFilesByEpicOut:
    return RunFilesByEpicOut.of(files_by_epic(ports, run_id))


@router.get(
    "/runs/{run_id}/files-by-epic/diff",
    response_model=StoryDiffOut,
    responses=REFUSALS,
    summary="Read one changed path's unified diff over a Story's attempts",
)
def get_story_diff(
    run_id: UUID,
    ports: Ports,
    epic: Annotated[int, Query(ge=0)],
    story: Annotated[str, Query(min_length=1)],
    path: Annotated[str, Query(min_length=1)],
) -> StoryDiffOut:
    return StoryDiffOut.of(story_diff(ports, run_id, epic, story, path))
