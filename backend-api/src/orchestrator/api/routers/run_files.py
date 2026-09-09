"""`GET`/`PUT /api/v1/runs/{run_id}/files` (story 6-2 read, story 6-3 tree + write): a look
inside a Run's own spec folder — what the spec-checkpoint body shows inline (6-2), and what
an Operator browses and edits from the Run detail screen's own ARTIFACTS column (6-3).

A router of its own, on the same `/runs` prefix `runs.py`/`run.py`/`run_detail.py`/
`signals.py` already share, for the same reason each of those already is: `runs.py` carries
its own frozen route-count test (`tests/unit/test_runs_router.py::
test_the_router_declares_exactly_the_two_operations`, pinned to `GET`/`POST /runs/
preflight`), so a third operation on that resource gets a new module rather than growing it
— exactly what `run_detail.py`'s and `signals.py`'s own docstrings already explain for
their own frozen siblings. The brief's own implementation note ("in `api/routers/
runs.py`") is an implementation note, not a binding rule; this is the honest alternative
that keeps the frozen test true. Mounted after `signals.router` in `main.py`.

**No `plan-diff` or any third operation here** (story 6-3's own Never list): this module
stays at exactly `GET` (read one file, list the tree with no `path`, or — with `diff=1`,
story 6-6 — answer one protected path's unified diff) and `PUT` (write one file while
parked). The diff is a *mode* on the read, not a route of its own, for the same reason the
tree is one: `test_run_files_router.py` pins this router at two operations, and a third
would be a route on a resource that has no room for one.
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
from orchestrator.api.providers import (
    run_files_diff_ports,
    run_files_ports,
    run_files_write_ports,
)
from orchestrator.api.schemas.run_files import (
    RunFileDiffOut,
    RunFileEntryOut,
    RunFileIn,
    RunFileOut,
    RunFilesTreeOut,
)
from orchestrator.application.use_cases.run_files import (
    RunFilesDiffPorts,
    RunFilesPorts,
    RunFilesWritePorts,
    diff_run_file,
    list_files_tree,
    read_run_file,
    write_run_file,
)

router = APIRouter(tags=["runs"])

Ports = Annotated[RunFilesPorts, Depends(run_files_ports)]
WritePorts = Annotated[RunFilesWritePorts, Depends(run_files_write_ports)]
#: `None` unless `diff=1` was asked for — the provider reads the mode itself, so an
#: ordinary read never opens the session a diff would need (`api/providers.py`).
DiffPorts = Annotated[RunFilesDiffPorts | None, Depends(run_files_diff_ports)]


def _refusal(description: str) -> dict[str, object]:
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


GET_REFUSALS = {
    403: _refusal(
        "The path is well formed but outside the Run's own spec folder — or, with "
        "`diff=1`, is not one of the protected paths this Run's park recorded."
    ),
    404: _refusal(
        "No Run has that id, no file is there, or — with `diff=1` — the parked step "
        "recorded no start commit to diff against."
    ),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The path escapes the workspace (`..`, or absolute)."),
}

PUT_REFUSALS = {
    403: _refusal("The path is well formed but outside the Run's own spec folder."),
    404: _refusal("No Run has that id."),
    409: _refusal(
        "The path names a list file the plan already read, or the Run is not parked "
        "without a terminal session."
    ),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The path escapes the workspace (`..`, or absolute)."),
}


@router.get(
    "/runs/{run_id}/files",
    response_model=RunFileOut | RunFilesTreeOut | RunFileDiffOut,
    summary="Read one file inside a Run's own spec folder, list its tree, or diff a hit",
    responses=GET_REFUSALS,
)
def get_file(
    run_id: UUID,
    ports: Ports,
    diff_ports: DiffPorts,
    path: Annotated[str | None, Query()] = None,
    diff: Annotated[bool, Query()] = False,
) -> RunFileOut | RunFilesTreeOut | RunFileDiffOut:
    """`path` omitted (6-3): every entry under the Run's own scope folder, recursively.
    `path` with `diff=1` (6-6): that protected path's unified diff, from the parked
    attempt's `start_sha` to the worktree. `path` alone (6-2, unchanged): the file, with a
    single-segment glob resolved here — see the use case's own docstring for each mode's
    refusal order."""
    if path is None:
        return RunFilesTreeOut.of(list_files_tree(ports, run_id))
    if diff and diff_ports is not None:
        return RunFileDiffOut.of(diff_run_file(diff_ports, run_id, path))
    return RunFileOut.of(read_run_file(ports, run_id, path))


@router.put(
    "/runs/{run_id}/files",
    response_model=RunFileEntryOut,
    summary="Write one file inside a Run's own spec folder while parked",
    responses=PUT_REFUSALS,
)
def put_file(run_id: UUID, body: RunFileIn, ports: WritePorts) -> RunFileEntryOut:
    """Commits `body.content` at `body.path` as `spec: operator edit (orchestrator)`,
    appends one `spec_edit` gate record, and answers the written row — see the use case's
    own docstring for the five checks and their order."""
    return RunFileEntryOut.of(write_run_file(ports, run_id, body.path, body.content))
