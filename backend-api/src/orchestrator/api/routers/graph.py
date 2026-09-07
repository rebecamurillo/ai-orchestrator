"""`/api/v1/templates/{name}/{version}/graph` — the shape of one Template Version (3.4).

A router of its own rather than a seventh route on `api/routers/templates.py`, for the
reason that module's own contract test states: it declares exactly the six operations that
*read and extend* Template Versions, and this one is about the shape of a version rather
than its text. `api/routers/clone_check.py` set the precedent; `main.py` mounts this one
with the same prefix and the same bearer dependency, so the split is invisible from outside
(AD-4). It is also where Epic 4's `GET /runs/{id}/graph` belongs — the run graph is this
graph with a status beside each node — which makes the split the destination, not a detour.

The path carries the same `version` bounds as `GET /templates/{name}/{version}`: a number
above `integer`'s range reaches the database as an out-of-range parameter, and refusing it
at the path keeps that a 422 rather than an unhandled driver error.

The 500 is the one refusal here that is not about the request. Storage only ever accepts
text that `validate()` passed, so a stored version that no longer validates is a defect in
this system rather than a caller's mistake — and it is answered as a problem document naming
the first `line` and `reason`, because "the stored Template is broken, at line 5" is what an
operator can act on, and a traceback is not. Every problem the validator found rides along
in `errors[]`, the same way `POST /templates/{name}/versions` reports its 422: one bad line
is rarely the only one, and a reader fixing the file needs the list, not the head of it.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path

from orchestrator.api.errors import (
    HTTP_INTERNAL_SERVER_ERROR,
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import run_view_ports, template_ports
from orchestrator.api.schemas.common import MAX_VERSION
from orchestrator.api.schemas.graph import GraphOut, RunGraphOut
from orchestrator.api.schemas.templates import as_problem_errors
from orchestrator.application.use_cases import templates as use_cases
from orchestrator.application.use_cases.run_views import RunViewPorts, run_graph_for
from orchestrator.application.use_cases.templates import StoredTemplateInvalid, TemplatePorts

router = APIRouter(tags=["templates"])

HTTP_NOT_FOUND = 404

#: The second route this module carries (module docstring): the run graph, keyed by Run id.
RUN_GRAPH_PATH = "/runs/{run_id}/graph"

#: One path, one operation today. Named so Epic 4's run graph lands beside it, not on it.
TEMPLATE_GRAPH_PATH = "/templates/{name}/{version}/graph"

#: The title every 500 this API sends already carries (`api/errors.py`). One status, one
#: title: `detail` and `errors[]` say which 500 it is, and nothing keys on a second phrase.
INTERNAL_TITLE = "internal server error"


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


# Every refusal is declared: left undeclared, FastAPI publishes its own
# `HTTPValidationError` schema for the 422, which
# `test_projects_router.py::test_every_published_refusal_is_the_problem_document_this_api_sends`
# checks — for the whole document — that this API never does.
REFUSALS = {
    HTTP_NOT_FOUND: _refusal("No Template has that name, or no version has that number."),
    HTTP_UNPROCESSABLE_CONTENT: _refusal("The version in the path is not a version number."),
    HTTP_INTERNAL_SERVER_ERROR: _refusal(
        "The stored Template no longer validates; `detail` names the first line and reason."
    ),
}

Ports = Annotated[TemplatePorts, Depends(template_ports)]


@router.get(
    TEMPLATE_GRAPH_PATH,
    response_model=GraphOut,
    summary="Read one Template Version's graph",
    responses=REFUSALS,
)
def template_graph(
    name: str, version: Annotated[int, Path(gt=0, le=MAX_VERSION)], ports: Ports
) -> GraphOut:
    """`{nodes, edges, groups}` from the one validator (AD-15). A call is one node."""
    try:
        graph = use_cases.template_graph(ports, name, version)
    except StoredTemplateInvalid as failure:
        first = failure.errors[0]
        raise Problem(
            status=HTTP_INTERNAL_SERVER_ERROR,
            title=INTERNAL_TITLE,
            detail=f"line {first.line}: {first.reason}",
            errors=as_problem_errors(failure.errors),
        ) from failure
    return GraphOut.of(graph)


RUN_NOT_FOUND = _refusal("No Run has that id.")
RUN_BAD_ID = _refusal("`run_id` does not parse as a UUID.")
RUN_REFUSALS = {HTTP_NOT_FOUND: RUN_NOT_FOUND, HTTP_UNPROCESSABLE_CONTENT: RUN_BAD_ID}

RunPorts = Annotated[RunViewPorts, Depends(run_view_ports)]


@router.get(
    RUN_GRAPH_PATH,
    response_model=RunGraphOut,
    summary="Read one Run's graph",
    responses=RUN_REFUSALS,
)
def run_graph(run_id: UUID, ports: RunPorts) -> RunGraphOut:
    """`build_run_graph` (SPEC CAP-12, AD-15): the planned rows, chained, grouped, coloured."""
    return RunGraphOut.of(run_graph_for(ports, run_id))
