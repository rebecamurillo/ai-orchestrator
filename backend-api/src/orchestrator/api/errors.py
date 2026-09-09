"""Every error leaves this API as one RFC 9457 problem document.

`{type, title, status, detail, instance, errors?}` with `application/problem+json`. The
web-client prints `detail` verbatim and puts each `errors[]` entry beside the field its
`path` names, so the shape is a contract and not a convenience: a router that answered with
a bare `{"detail": ...}` would be invisible to that rendering.

Six things can go wrong, and each has exactly one handler here:

- `Problem` — raised by a router or a dependency that already knows the status it wants.
- `RequestValidationError` — Pydantic refused the request; FastAPI's own `loc`/`msg` shape
  is replaced so the browser never has to understand it.
- `ResponseValidationError` — this service produced a payload its own response model
  refuses. A different class from the request case, and without its own handler it escapes
  as plain text.
- `HTTPException` — Starlette's own 404 and 405, which would otherwise be JSON of a
  different shape.
- `DomainError` — a use case reported a described outcome. `domain/` may not import
  `fastapi` (AD-2), so this module is the single place that knows the status of each kind.
- `Exception` — anything left is a bug. It is still answered as a problem document, with
  the traceback in the log and nothing of it in the body; the alternative is Starlette's
  `text/plain` 500, which is exactly the shape the Schemathesis gate exists to catch.

No handler asserts its argument's type. Handlers are registered against the class they
name, and `python -O` strips `assert` — a check that disappears under an optimisation flag
is not a check.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from orchestrator.domain.errors import Conflict, DomainError, Forbidden, Invalid, NotFound

log = structlog.get_logger(__name__)

PROBLEM_MEDIA_TYPE = "application/problem+json"

#: RFC 9457 §4.2.1 — "no further semantics than the status code".
ABOUT_BLANK = "about:blank"

HTTP_UNPROCESSABLE_CONTENT = 422
HTTP_BAD_REQUEST = 400
HTTP_INTERNAL_SERVER_ERROR = 500

#: The `loc` of a failure that names no field at all — a body that is not an object.
WHOLE_BODY = "body"

#: The one place a domain outcome becomes a status code.
DOMAIN_STATUS: tuple[tuple[type[DomainError], int, str], ...] = (
    (NotFound, HTTPStatus.NOT_FOUND, "not found"),
    (Forbidden, HTTPStatus.FORBIDDEN, "forbidden"),
    (Conflict, HTTPStatus.CONFLICT, "conflict"),
    (Invalid, HTTP_UNPROCESSABLE_CONTENT, "invalid"),
)


class ProblemError(BaseModel):
    """One entry of `errors[]`.

    `reason` is always present; the rest name where the reason applies — a request field
    (`path`) or a place in a workflow template (`template`, `version`, `line`).
    """

    template: str | None = None
    version: str | None = None
    line: int | None = None
    path: str | None = None
    reason: str


class ProblemDetail(BaseModel):
    """The problem document itself. Members that do not apply are omitted, never `null`."""

    type: str = ABOUT_BLANK
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
    errors: list[ProblemError] | None = None

    def as_body(self) -> dict[str, Any]:
        """The JSON body: only the members that carry something."""
        return self.model_dump(exclude_none=True)


class Problem(Exception):
    """An error a router or dependency raises when it already knows the status.

    Named for the RFC 9457 document it becomes, not for the `...Error` convention.
    """

    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str | None = None,
        errors: list[ProblemError] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or title)
        self.status = status
        self.title = title
        self.detail = detail
        self.errors = errors
        # RFC 9457's `type` member. Every problem this system raises so far is fully
        # described by its status, which is what `about:blank` means; a story that
        # introduces a documented problem type assigns this attribute.
        self.type = ABOUT_BLANK
        # response headers the status requires — a 401 must carry a challenge (RFC 9110
        # §15.5.2). They never vary the body, so two refusals stay byte-identical.
        self.headers = headers

    def as_detail(self, instance: str | None = None) -> ProblemDetail:
        return ProblemDetail(
            type=self.type,
            title=self.title,
            status=self.status,
            detail=self.detail,
            instance=instance,
            errors=self.errors,
        )


#: A reference to the problem schema, for responses that declare their media type by hand.
PROBLEM_SCHEMA_REF = {"$ref": "#/components/schemas/ProblemDetail"}

#: The 401 every versioned route can answer, declared so `/openapi.json` describes the
#: error shape web-client generates its types from in 1.3 (AD-3).
#:
#: `model` is what registers `ProblemDetail` in `components.schemas`; FastAPI then also
#: lists the schema under the route's own response media type (`application/json`), because
#: an additional response has no way to override it. The explicit `content` entry below is
#: the one that matches what the server actually sends.
UNAUTHORIZED_RESPONSE = {
    "model": ProblemDetail,
    "description": "The request carried no valid ORCHESTRATOR_TOKEN.",
    "content": {PROBLEM_MEDIA_TYPE: {"schema": PROBLEM_SCHEMA_REF}},
}


def problem_response(detail: ProblemDetail, headers: dict[str, str] | None = None) -> Response:
    """Render a problem document with the media type that makes it machine-readable."""
    return JSONResponse(
        status_code=detail.status,
        content=detail.as_body(),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _error_path(location: tuple[Any, ...]) -> str:
    """`("body", "count")` -> `body.count` — the key the web-client puts the message beside.

    An empty location means the whole body was refused; naming it `body` keeps `detail`
    from reading `": <reason>"` and gives the client something to attach the message to.
    """
    return ".".join(str(part) for part in location) or WHOLE_BODY


def _phrase(status: int) -> str:
    """`404` -> `not found`. Lowercase because the API's voice has no title case."""
    try:
        return HTTPStatus(status).phrase.lower()
    except ValueError:  # pragma: no cover — a non-standard status is not raised anywhere
        return "error"


async def _handle_problem(request: Request, exc: Problem) -> Response:
    return problem_response(exc.as_detail(instance=request.url.path), headers=exc.headers)


async def _handle_validation_error(request: Request, exc: RequestValidationError) -> Response:
    errors = [
        ProblemError(path=_error_path(entry.get("loc", ())), reason=str(entry.get("msg", "")))
        for entry in exc.errors()
    ]
    first = errors[0] if errors else None
    return problem_response(
        ProblemDetail(
            title="validation failed",
            status=HTTP_UNPROCESSABLE_CONTENT,
            detail=f"{first.path}: {first.reason}" if first else None,
            instance=request.url.path,
            errors=errors or None,
        )
    )


async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> Response:
    title = _phrase(exc.status_code)
    detail = str(exc.detail) if exc.detail else None
    # Starlette's default detail is the status phrase; repeating it says nothing
    if detail is not None and detail.lower() == title:
        detail = None
    return problem_response(
        ProblemDetail(
            title=title,
            status=exc.status_code,
            detail=detail,
            instance=request.url.path,
        ),
        headers=dict(exc.headers) if exc.headers else None,
    )


async def _handle_domain_error(request: Request, exc: DomainError) -> Response:
    status, title = HTTP_BAD_REQUEST, "bad request"
    for kind, mapped_status, mapped_title in DOMAIN_STATUS:
        if isinstance(exc, kind):
            status, title = mapped_status, mapped_title
            break
    return problem_response(
        ProblemDetail(
            title=title,
            status=status,
            detail=str(exc) or None,
            instance=request.url.path,
        )
    )


async def _handle_response_validation_error(
    request: Request, exc: ResponseValidationError
) -> Response:
    """This service built a payload its own response model refuses — a bug, reported as one."""
    log.exception("response validation failed", path=request.url.path)
    return problem_response(
        ProblemDetail(
            title="internal server error",
            status=HTTP_INTERNAL_SERVER_ERROR,
            instance=request.url.path,
        )
    )


async def _handle_unexpected(request: Request, exc: Exception) -> Response:
    """Anything with no handler of its own. The traceback is logged; the body says nothing.

    Without this the answer is Starlette's `text/plain` 500 — a different content type, a
    different shape, and a stack trace's worth of internals in the `debug` case.
    """
    log.exception("unhandled error", path=request.url.path)
    return problem_response(
        ProblemDetail(
            title="internal server error",
            status=HTTP_INTERNAL_SERVER_ERROR,
            instance=request.url.path,
        )
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register every handler. Called once, by `create_app`."""
    app.add_exception_handler(Problem, _handle_problem)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(ResponseValidationError, _handle_response_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(DomainError, _handle_domain_error)
    # Starlette's own server-error hook: it sends this response and then re-raises so the
    # process still logs the failure
    app.add_exception_handler(Exception, _handle_unexpected)
