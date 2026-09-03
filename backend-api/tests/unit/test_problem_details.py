"""One error shape for the whole API — RFC 9457 `application/problem+json`.

The web-client's form handling reads `detail` verbatim and places `errors[]` beside the
field each entry names (Consistency Conventions — Form errors), so the shape is a contract,
not a convenience. Every path out of the application funnels through the handlers installed
here: a raised `Problem`, a Pydantic validation failure, a Starlette `HTTPException` (the
404 for an unknown path), and a `DomainError` from a use case.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from orchestrator.api.errors import (
    PROBLEM_MEDIA_TYPE,
    Problem,
    ProblemDetail,
    ProblemError,
    _error_path,
    install_error_handlers,
)
from orchestrator.domain.errors import Conflict, DomainError, Invalid, NotFound

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_SERVER_ERROR = 500

PROBLEM_KEYS = {"type", "title", "status", "detail", "instance", "errors"}


class Counted(BaseModel):
    """A body with one required integer, so validation has something to fail on."""

    count: int


def _app() -> FastAPI:
    """A throwaway application carrying one route per error path under test."""
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/raises-problem")
    def raises_problem() -> None:
        raise Problem(status=HTTP_UNAUTHORIZED, title="unauthorized")

    @app.get("/raises-problem-with-errors")
    def raises_problem_with_errors() -> None:
        raise Problem(
            status=HTTP_UNPROCESSABLE,
            title="invalid template",
            detail="dev-loop@1:12: unknown step kind",
            errors=[ProblemError(template="dev-loop", version="1", line=12, reason="unknown kind")],
        )

    @app.get("/raises/{kind}")
    def raises_domain_error(kind: str) -> None:
        errors: dict[str, type[DomainError]] = {
            "not-found": NotFound,
            "conflict": Conflict,
            "invalid": Invalid,
            "base": DomainError,
        }
        raise errors[kind](f"run 7 {kind}")

    @app.post("/validated")
    def validated(body: Counted) -> dict[str, int]:
        return {"count": body.count}

    @app.get("/whole-body")
    def whole_body(body: Counted) -> dict[str, int]:
        return {"count": body.count}

    @app.get("/bug")
    def bug() -> None:
        raise ZeroDivisionError("a divisor nobody checked")

    @app.get("/wrong-response", response_model=Counted)
    def wrong_response() -> dict[str, str]:
        # the route promises a Counted and returns something else: a bug in this service
        return {"count": "not a number"}

    return app


async def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    # raise_app_exceptions=False: Starlette's server-error hook sends the response and then
    # re-raises so the process still logs the failure. The client sees the response.
    transport = httpx.ASGITransport(app=_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.request(method, path, **kwargs)


# ── the model ────────────────────────────────────────────────────────────────


def test_the_problem_document_carries_exactly_the_declared_members() -> None:
    assert set(ProblemDetail.model_fields) == PROBLEM_KEYS


def test_an_error_entry_carries_exactly_the_declared_members() -> None:
    assert set(ProblemError.model_fields) == {"template", "version", "line", "path", "reason"}


def test_only_the_reason_of_an_error_entry_is_required() -> None:
    entry = ProblemError(reason="unknown kind")

    assert entry.reason == "unknown kind"
    assert entry.path is None


def test_type_defaults_to_about_blank() -> None:
    """RFC 9457 §4.2.1: `about:blank` means "no further semantics than the status code"."""
    assert ProblemDetail(title="unauthorized", status=HTTP_UNAUTHORIZED).type == "about:blank"


def test_absent_members_are_left_out_of_the_body_rather_than_sent_as_null() -> None:
    detail = ProblemDetail(title="unauthorized", status=HTTP_UNAUTHORIZED)

    assert detail.as_body() == {
        "type": "about:blank",
        "title": "unauthorized",
        "status": HTTP_UNAUTHORIZED,
    }


# ── a raised Problem ─────────────────────────────────────────────────────────


def test_a_problem_carries_its_own_status_and_media_type() -> None:
    assert PROBLEM_MEDIA_TYPE == "application/problem+json"


async def test_a_raised_problem_becomes_a_problem_response() -> None:
    response = await _request("GET", "/raises-problem")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json() == {
        "type": "about:blank",
        "title": "unauthorized",
        "status": HTTP_UNAUTHORIZED,
        "instance": "/raises-problem",
    }


async def test_a_problem_may_carry_structured_errors() -> None:
    response = await _request("GET", "/raises-problem-with-errors")
    body = response.json()

    assert response.status_code == HTTP_UNPROCESSABLE
    assert body["detail"] == "dev-loop@1:12: unknown step kind"
    assert body["errors"] == [
        {"template": "dev-loop", "version": "1", "line": 12, "reason": "unknown kind"}
    ]


def test_a_problem_is_an_exception_so_a_router_can_raise_it() -> None:
    with pytest.raises(Problem) as raised:
        raise Problem(status=HTTP_CONFLICT, title="conflict", detail="run is not queued")

    assert raised.value.status == HTTP_CONFLICT
    assert "run is not queued" in str(raised.value)


# ── validation ───────────────────────────────────────────────────────────────


async def test_a_validation_failure_is_a_problem_not_fastapis_default_shape() -> None:
    response = await _request("POST", "/validated", json={"count": "not a number"})
    body = response.json()

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert body["title"] == "validation failed"
    # FastAPI's own key, which the web-client must never have to understand
    assert "loc" not in response.text


async def test_a_validation_failure_names_the_field_and_the_reason() -> None:
    response = await _request("POST", "/validated", json={"count": "not a number"})
    body = response.json()

    assert body["errors"] == [
        {"path": "body.count", "reason": body["errors"][0]["reason"]},
    ]
    assert body["errors"][0]["reason"]


async def test_the_detail_names_the_first_error() -> None:
    response = await _request("POST", "/validated", json={})
    body = response.json()

    first = body["errors"][0]
    assert body["detail"] == f"{first['path']}: {first['reason']}"


async def test_every_failing_field_gets_an_entry() -> None:
    response = await _request("POST", "/validated", json={"count": None})
    body = response.json()

    assert len(body["errors"]) == 1
    assert body["errors"][0]["path"] == "body.count"


def test_a_failure_naming_no_field_falls_back_to_body() -> None:
    """An empty `loc` would make `detail` read `": <reason>"` and leave `path` blank."""
    assert _error_path(()) == "body"
    assert _error_path(("body", "count")) == "body.count"
    assert _error_path(("body", 0, "name")) == "body.0.name"


async def test_an_unparseable_body_still_names_a_path_and_a_detail() -> None:
    response = await _request("GET", "/whole-body", content=b"not json at all")
    body = response.json()

    assert response.status_code == HTTP_UNPROCESSABLE
    assert body["errors"][0]["path"]
    assert not body["detail"].startswith(":")


async def test_a_valid_body_still_passes() -> None:
    response = await _request("POST", "/validated", json={"count": 3})

    assert response.status_code == HTTP_OK
    assert response.json() == {"count": 3}


# ── HTTPException, including the framework's own 404 ─────────────────────────


async def test_an_unknown_path_answers_with_a_problem_document() -> None:
    """Starlette's default is a bare `{"detail": "Not Found"}`; the API has one shape."""
    response = await _request("GET", "/no-such-path")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "not found"
    assert response.json()["instance"] == "/no-such-path"


async def test_a_wrong_method_answers_with_a_problem_document() -> None:
    response = await _request("DELETE", "/raises-problem")

    assert response.status_code == HTTP_METHOD_NOT_ALLOWED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert set(response.json()) <= PROBLEM_KEYS


# ── domain errors ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("kind", "status", "title"),
    [
        ("not-found", HTTP_NOT_FOUND, "not found"),
        ("conflict", HTTP_CONFLICT, "conflict"),
        ("invalid", HTTP_UNPROCESSABLE, "invalid"),
    ],
)
async def test_a_domain_error_maps_to_its_status(kind: str, status: int, title: str) -> None:
    response = await _request("GET", f"/raises/{kind}")
    body = response.json()

    assert response.status_code == status
    assert body["title"] == title
    assert body["detail"] == f"run 7 {kind}"
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_an_unmapped_domain_error_is_a_client_error_not_a_500() -> None:
    """A `DomainError` is always a described outcome; only a bug is a 5xx."""
    response = await _request("GET", "/raises/base")

    assert HTTP_BAD_REQUEST <= response.status_code < HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


def test_every_handler_the_api_needs_is_installed() -> None:
    app = _app()

    for exception in (
        Problem,
        RequestValidationError,
        ResponseValidationError,
        StarletteHTTPException,
        DomainError,
        Exception,
    ):
        assert exception in app.exception_handlers, exception


# ── the paths that would otherwise escape as plain text ──────────────────────


async def test_an_unhandled_exception_is_still_a_problem_document() -> None:
    """Starlette's default is `text/plain` — the very shape the e2e gate exists to catch."""
    response = await _request("GET", "/bug")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "internal server error"


async def test_an_unhandled_exception_leaks_no_internals() -> None:
    """The traceback belongs in the log; the body says nothing an attacker can use."""
    response = await _request("GET", "/bug")
    body = response.json()

    assert "detail" not in body
    assert "ZeroDivisionError" not in response.text
    assert "divisor" not in response.text
    assert "Traceback" not in response.text


async def test_a_response_that_fails_its_own_model_is_a_problem_document() -> None:
    """`ResponseValidationError` is not a `RequestValidationError`; it needs its own handler."""
    response = await _request("GET", "/wrong-response")

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "internal server error"


async def test_a_response_validation_failure_leaks_no_internals() -> None:
    response = await _request("GET", "/wrong-response")

    assert "not a number" not in response.text
    assert set(response.json()) <= PROBLEM_KEYS


# ── headers a status requires ────────────────────────────────────────────────


async def test_a_problem_may_carry_response_headers() -> None:
    """A 401 must carry a challenge; headers vary nothing about the body."""
    app = FastAPI()
    install_error_handlers(app)

    @app.get("/challenged")
    def challenged() -> None:
        raise Problem(
            status=HTTP_UNAUTHORIZED, title="unauthorized", headers={"WWW-Authenticate": "Bearer"}
        )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get("/challenged")

    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "type": "about:blank",
        "title": "unauthorized",
        "status": HTTP_UNAUTHORIZED,
        "instance": "/challenged",
    }


async def test_a_problem_without_headers_sends_none() -> None:
    response = await _request("GET", "/raises-problem")

    assert "www-authenticate" not in response.headers
