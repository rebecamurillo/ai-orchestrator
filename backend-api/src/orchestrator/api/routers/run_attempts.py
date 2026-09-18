"""`GET /api/v1/runs/{run_id}/attempts/{attempt_id}/log` (story 1-1): byte-cursor paging
and raw-download of one attempt's log file.

All access is via the web-client catch-all proxy; the browser never reaches the log
volume directly (AD-1).  The route is read-only and writes no status anywhere (AD-8).
It reuses `Depends(run_view_ports)` — `RunViewPorts` already carries both `attempts`
and `logs` — so no new provider function is needed in `providers.py`.

`?download=true` streams the full raw file; the default paged form returns a
`LogPageOut` JSON body addressed by byte offset.  Both answer 200 when the log was
garbage-collected, never 4xx/5xx for a missing file.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from orchestrator.api.errors import (
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import run_view_ports
from orchestrator.api.schemas.run_attempts import LogPageOut
from orchestrator.application.use_cases.run_view_types import RunViewPorts

router = APIRouter(tags=["runs"])

Ports = Annotated[RunViewPorts, Depends(run_view_ports)]
Cursor = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=5000)]

HTTP_NOT_FOUND = 404

_TEXT_PLAIN = "text/plain; charset=utf-8"
_GC_MESSAGE = b"log no longer on disk"


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


REFUSALS: dict[int, object] = {
    HTTP_NOT_FOUND: _refusal("No attempt with that id in this Run."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("A path segment does not parse as a UUID."),
}


@router.get(
    "/runs/{run_id}/attempts/{attempt_id}/log",
    response_model=None,
    summary="Read one attempt's log, paged by byte offset",
    responses={200: {"model": LogPageOut}, **REFUSALS},
)
def log_page(  # noqa: PLR0913, PLR0917
    run_id: UUID,
    attempt_id: UUID,
    ports: Ports,
    cursor: Cursor = 0,
    limit: Limit = 200,
    download: bool = False,
) -> LogPageOut | Response:
    """Page through an attempt's log by byte cursor, or download the full file.

    Returns `LogPageOut` JSON when `download` is absent or false.  Returns a
    `text/plain` attachment when `?download=true`.  Both variants answer 200 with a
    human-readable message when the file has been garbage-collected.
    """
    attempt = ports.attempts.get(attempt_id)
    if attempt is None or attempt.run_id != run_id:
        raise Problem(status=HTTP_NOT_FOUND, title="No attempt with that id in this Run.")

    if attempt.log_path is None:
        if download:
            return Response(content=b"", media_type=_TEXT_PLAIN)
        return LogPageOut(lines=[], next_cursor=0, eof=True)

    if download:
        raw = ports.logs.read_raw(attempt.log_path)
        if raw is None:
            return Response(content=_GC_MESSAGE, media_type=_TEXT_PLAIN)
        return Response(
            content=raw,
            media_type=_TEXT_PLAIN,
            headers={"Content-Disposition": f'attachment; filename="{attempt_id}.log"'},
        )

    result = ports.logs.read_from(attempt.log_path, cursor, limit)
    if result is None:
        return LogPageOut(lines=["log no longer on disk"], next_cursor=0, eof=True)
    lines, next_cursor, eof = result
    return LogPageOut(lines=lines, next_cursor=next_cursor, eof=eof)
