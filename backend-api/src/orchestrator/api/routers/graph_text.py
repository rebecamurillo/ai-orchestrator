"""`/api/v1/templates/{name}/graph` — the shape of posted YAML, and of the latest stored
version (3.6).

A third router for a third path, and the split is forced twice over rather than chosen.
It is not on `api/routers/graph.py`, whose own contract test asserts that **every** route
there includes `GET` — `api/routers/graph.py` is where the *version* graph and Epic 4's run
graph live, and both are reads. It is not on `api/routers/templates.py` either, whose
contract test asserts an exact six-entry route list of the operations that read and extend
Template Versions. Both are anchors and both stay literally true; `api/routers/clone_check.py`
set the precedent, and `main.py` mounts this one with the same prefix and the same bearer
dependency, so the split is invisible from outside — one path, two operations, one
credential (AD-4).

The mount goes **before** `templates.router`. Starlette matches in registration order, and
`templates.router` registers `GET /templates/{name}/{version}` last, so a three-segment
`GET /templates/{name}/graph` mounted after it would be swallowed as `version="graph"` and
answered 422. `main.py`'s own comment names that, and
`tests/unit/test_graph_text_router.py` asserts the order over the built application.

The `POST` is what the Templates screen's diagram is drawn from: the editor holds text that
is not stored yet, so a diagram that could only be built from a stored version would be one
save behind what the Operator is reading. Text that does not validate has no graph at all,
which is why this route *refuses* with the validator's errors where
`POST /templates/{name}/validate` reports them as data — there, the caller asked what is
wrong; here, the caller asked for a picture. The mapping is `save_version`'s, verbatim.

The `GET` beside it is mandatory rather than decorative: `tests/unit/test_bearer_auth.py`
indexes `document["paths"][path]["get"]` for every published `/api/v1` path. It answers the
latest stored version's graph — the exact mirror of `GET /templates/{name}/validate` — and
carries the same 500 `api/routers/graph.py` does, for the same reason: storage only ever
accepts text `validate()` passed, so a stored version that no longer validates is a defect
in this system rather than a caller's mistake, and an operator can act on "the stored
Template is broken, at line 5" where a traceback tells them nothing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from orchestrator.api.errors import (
    HTTP_INTERNAL_SERVER_ERROR,
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM_MEDIA_TYPE,
    PROBLEM_SCHEMA_REF,
    Problem,
    ProblemDetail,
)
from orchestrator.api.providers import template_ports
from orchestrator.api.schemas.graph import GraphOut, GraphTextIn
from orchestrator.api.schemas.templates import as_problem_errors
from orchestrator.application.use_cases import templates as use_cases
from orchestrator.application.use_cases.templates import (
    StoredTemplateInvalid,
    TemplatePorts,
    TemplateValidationFailed,
)

router = APIRouter(tags=["templates"])

HTTP_NOT_FOUND = 404

#: One path, two operations. Named once so the `POST` and the `GET` cannot drift apart.
TEMPLATE_TEXT_GRAPH_PATH = "/templates/{name}/graph"

#: The title every 500 this API sends already carries (`api/errors.py`). One status, one
#: title: `detail` and `errors[]` say which 500 it is, and nothing keys on a second phrase.
INTERNAL_TITLE = "internal server error"

#: The title `POST /templates/{name}/versions` already sends for text that did not validate.
INVALID_TITLE = "invalid template"


def _refusal(description: str) -> dict[str, object]:
    """One declared error response, in the shape this API actually sends."""
    return {
        "model": ProblemDetail,
        "description": description,
        "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
    }


NOT_FOUND_RESPONSE = _refusal("No Template has that name.")

# Every refusal is declared: left undeclared, FastAPI publishes its own
# `HTTPValidationError` schema for the 422, which
# `test_projects_router.py::test_every_published_refusal_is_the_problem_document_this_api_sends`
# checks — for the whole document — that this API never does.
# No 404 on the `POST`: it reads no version by name. The path segment is where the screen
# is open, not a lookup — the same reason `POST /templates/{name}/validate` declares only
# its 422.
POST_REFUSALS = {
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "The posted YAML has no graph; `errors[]` names each problem by line."
    ),
}
GET_REFUSALS = {
    HTTP_NOT_FOUND: NOT_FOUND_RESPONSE,
    # Declared because FastAPI publishes a 422 for any operation carrying a parameter, and
    # an undeclared one would be its own `HTTPValidationError` shape. Nothing this
    # operation reads can produce it: `name` is an unconstrained path segment.
    HTTP_UNPROCESSABLE_CONTENT: _refusal(
        "The framework's own request-validation refusal, in the shape this API sends."
    ),
    HTTP_INTERNAL_SERVER_ERROR: _refusal(
        "The stored Template no longer validates; `detail` names the first line and reason."
    ),
}

Ports = Annotated[TemplatePorts, Depends(template_ports)]


@router.post(
    TEMPLATE_TEXT_GRAPH_PATH,
    response_model=GraphOut,
    summary="Build the graph of posted Template YAML",
    responses=POST_REFUSALS,
)
def graph_text(name: str, payload: GraphTextIn, ports: Ports) -> GraphOut:
    """`{nodes, edges, groups}` from the one validator (AD-15). Nothing is stored.

    `name` is the path segment the Templates screen is open at. It is not checked against
    the posted text's own `name:`, because the editor is free to hold a rename in progress
    and a diagram of what is on screen is exactly what this route is for; the save route is
    where that rule belongs, and it already carries it.
    """
    try:
        graph = use_cases.graph_text(ports, payload.yaml)
    except TemplateValidationFailed as failure:
        raise _invalid(failure) from failure
    return GraphOut.of(graph)


@router.get(
    TEMPLATE_TEXT_GRAPH_PATH,
    response_model=GraphOut,
    summary="Read the latest stored Version's graph",
    responses=GET_REFUSALS,
)
def graph_latest(name: str, ports: Ports) -> GraphOut:
    """The latest stored version's shape, and no write. An unknown name is a 404."""
    try:
        graph = use_cases.graph_latest(ports, name)
    except StoredTemplateInvalid as failure:
        raise _stored_invalid(failure) from failure
    return GraphOut.of(graph)


def _invalid(failure: TemplateValidationFailed) -> Problem:
    """The 422 `save_version` sends, built from the same errors."""
    first = failure.errors[0]
    return Problem(
        status=HTTP_UNPROCESSABLE_CONTENT,
        title=INVALID_TITLE,
        detail=f"line {first.line}: {first.reason}",
        errors=as_problem_errors(failure.errors),
    )


def _stored_invalid(failure: StoredTemplateInvalid) -> Problem:
    """The 500 `api/routers/graph.py` sends, built from the same errors."""
    first = failure.errors[0]
    return Problem(
        status=HTTP_INTERNAL_SERVER_ERROR,
        title=INTERNAL_TITLE,
        detail=f"line {first.line}: {first.reason}",
        errors=as_problem_errors(failure.errors),
    )
