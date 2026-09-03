"""One credential guards every versioned route (AD-4).

`ORCHESTRATOR_TOKEN` is the only login this system has. Two properties matter and neither is
visible by reading a router: the comparison is constant-time, so a wrong token cannot be
found a byte at a time; and *every* `/api/v1` route carries the dependency, so a router
added in a later story cannot forget it. Both are asserted structurally below, alongside the
401 rows of the story's edge-case matrix.

A third property is easy to lose and catastrophic: `hmac.compare_digest(b"", b"")` is
`True`, so an instance whose `ORCHESTRATOR_TOKEN` is empty would accept every request that
sends no credential at all. That case is asserted directly.

`/healthz` and `/openapi.json` stay public: the container healthcheck and the contract
export in 1.3 have no token.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
from typing import Annotated, Any

import httpx
import pytest
from fastapi import Depends, FastAPI

from orchestrator import main as composition_root
from orchestrator.api import deps
from orchestrator.api.deps import require_bearer
from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, install_error_handlers
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_SERVER_ERROR = 500

API_PREFIX = "/api/v1"
PUBLIC_PATHS = ("/healthz", "/openapi.json")
PROBLEM_MEDIA = "application/problem+json"


async def _request(path: str, headers: Any = None) -> httpx.Response:
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path, headers=headers)


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── the route itself ─────────────────────────────────────────────────────────


async def test_ping_answers_with_the_correct_bearer(env: dict[str, str]) -> None:
    response = await _request(f"{API_PREFIX}/ping", _bearer(env["ORCHESTRATOR_TOKEN"]))

    assert response.status_code == HTTP_OK
    assert response.json() == {"pong": True}


@pytest.mark.parametrize("path", PUBLIC_PATHS)
async def test_the_public_paths_need_no_token(env: dict[str, str], path: str) -> None:
    response = await _request(path)

    assert response.status_code == HTTP_OK


# ── the 401 rows of the matrix ───────────────────────────────────────────────


async def test_a_missing_header_is_refused(env: dict[str, str]) -> None:
    response = await _request(f"{API_PREFIX}/ping")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "unauthorized"


@pytest.mark.parametrize(
    "header",
    [
        {"Authorization": "Basic abc"},
        {"Authorization": "Bearer"},
        {"Authorization": ""},
    ],
    ids=["wrong-scheme", "no-credential", "empty"],
)
async def test_a_malformed_header_is_refused(env: dict[str, str], header: dict[str, str]) -> None:
    response = await _request(f"{API_PREFIX}/ping", header)

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_a_token_differing_by_one_byte_is_refused(env: dict[str, str]) -> None:
    token = env["ORCHESTRATOR_TOKEN"]
    nearly = token[:-1] + ("x" if token[-1] != "x" else "y")

    assert len(nearly) == len(token)

    response = await _request(f"{API_PREFIX}/ping", _bearer(nearly))

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_a_non_ascii_token_is_a_401_not_a_500(env: dict[str, str]) -> None:
    """`hmac.compare_digest` raises TypeError on a non-ASCII `str`; bytes are compared.

    The header is sent as bytes because a header is latin-1 on the wire — which is exactly
    how a junk `Authorization` reaches the dependency in production.
    """
    response = await _request(
        f"{API_PREFIX}/ping", {"Authorization": "Bearer ünicode".encode("latin-1")}
    )

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_a_prefix_of_the_token_is_refused(env: dict[str, str]) -> None:
    response = await _request(f"{API_PREFIX}/ping", _bearer(env["ORCHESTRATOR_TOKEN"][:-1]))

    assert response.status_code == HTTP_UNAUTHORIZED


async def test_every_refusal_answers_with_the_same_body(env: dict[str, str]) -> None:
    """Nothing in the *body* may tell an attacker which of the mistakes was made.

    The 401 now carries a `WWW-Authenticate` header, so the body is the only thing left
    that could vary between the cases. Every case is compared byte for byte.
    """
    missing = await _request(f"{API_PREFIX}/ping")
    wrong = await _request(f"{API_PREFIX}/ping", _bearer("a-token-that-is-not-the-token"))
    scheme = await _request(f"{API_PREFIX}/ping", {"Authorization": "Basic abc"})
    junk = await _request(
        f"{API_PREFIX}/ping", {"Authorization": "Bearer ünicode".encode("latin-1")}
    )
    empty = await _request(f"{API_PREFIX}/ping", {"Authorization": ""})

    bodies = {missing.content, wrong.content, scheme.content, junk.content, empty.content}
    assert len(bodies) == 1, bodies


async def test_an_empty_configured_token_refuses_everything(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """`compare_digest(b"", b"")` is True: a blank instance token would open the whole API."""
    monkeypatch.setenv("ORCHESTRATOR_TOKEN", "")
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        no_header = await client.get(f"{API_PREFIX}/ping")
        empty_bearer = await client.get(f"{API_PREFIX}/ping", headers={"Authorization": "Bearer "})

    assert no_header.status_code == HTTP_UNAUTHORIZED
    assert empty_bearer.status_code == HTTP_UNAUTHORIZED
    assert no_header.json()["title"] == "unauthorized"


async def test_the_refusal_carries_the_challenge_a_401_requires(env: dict[str, str]) -> None:
    """RFC 9110 §15.5.2: a 401 must carry `WWW-Authenticate`. `auto_error=False` removed
    the one FastAPI would have sent, so the dependency sends it."""
    response = await _request(f"{API_PREFIX}/ping")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["www-authenticate"] == "Bearer"


async def test_the_challenge_names_no_realm_or_scope(env: dict[str, str]) -> None:
    """A realm is one more thing to probe, and this instance has exactly one credential."""
    response = await _request(f"{API_PREFIX}/ping")

    assert "realm" not in response.headers["www-authenticate"].lower()


async def test_the_refusal_never_echoes_the_token(env: dict[str, str]) -> None:
    token = env["ORCHESTRATOR_TOKEN"]

    response = await _request(f"{API_PREFIX}/ping", _bearer(token))
    refusal = await _request(f"{API_PREFIX}/ping", _bearer("wrong"))

    assert token not in refusal.text
    assert "wrong" not in refusal.text
    assert response.status_code == HTTP_OK


# ── the structural guarantees ────────────────────────────────────────────────


def _versioned_operations(document: dict[str, Any]) -> list[tuple[str, str]]:
    """Every `(method, path)` the contract publishes under `/api/v1`.

    Read from the OpenAPI document rather than from FastAPI's route objects: the document
    is the published surface (AD-3), and it stays the same shape whatever the framework
    does internally with `include_router`.
    """
    return [
        (method, path)
        for path, operations in document.get("paths", {}).items()
        if path.startswith(API_PREFIX)
        for method in operations
        if method in ("get", "post", "put", "patch", "delete")
    ]


def _concrete(path: str) -> str:
    """Fill any `{id}` segment, so an operation can actually be called."""
    parts = [
        "01a06887-79ab-759b-97a0-71c32ad939c2" if part.startswith("{") else part
        for part in path.split("/")
    ]
    return "/".join(parts)


async def _document(env: dict[str, str]) -> dict[str, Any]:
    response = await _request("/openapi.json")
    return dict(response.json())


async def test_the_contract_publishes_versioned_operations_to_check(env: dict[str, str]) -> None:
    """Without this, the sweep below would pass over an empty list."""
    assert _versioned_operations(await _document(env))


async def test_every_versioned_operation_refuses_an_unauthenticated_call(
    env: dict[str, str],
) -> None:
    """A feature router added later without the dependency fails here, not in production."""
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        for method, path in _versioned_operations(await _document(env)):
            response = await client.request(method, _concrete(path))

            assert response.status_code == HTTP_UNAUTHORIZED, f"{method} {path}"
            assert response.json()["title"] == "unauthorized", f"{method} {path}"


async def test_the_scheme_is_published_so_the_contract_describes_the_bearer(
    env: dict[str, str],
) -> None:
    """1.3 generates the client from this document; the bearer has to be in it."""
    schemes = (await _document(env))["components"]["securitySchemes"]

    assert any(
        scheme.get("type") == "http" and scheme.get("scheme") == "bearer"
        for scheme in schemes.values()
    )


def test_the_versioned_router_is_mounted_with_the_dependency(env: dict[str, str]) -> None:
    """The check is attached to the whole prefix, not repeated on each route."""
    tree = ast.parse(inspect.getsource(composition_root))
    mounts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "include_router"
    ]

    assert mounts
    for mount in mounts:
        keywords = {keyword.arg: ast.unparse(keyword.value) for keyword in mount.keywords}
        assert keywords.get("prefix") == "API_PREFIX", ast.unparse(mount)
        assert "require_bearer" in keywords.get("dependencies", ""), ast.unparse(mount)


async def test_the_contract_declares_the_401_and_its_media_type(env: dict[str, str]) -> None:
    """1.3 generates the client from this document; the error shape has to be in it."""
    document = await _document(env)

    for _method, path in _versioned_operations(document):
        responses = document["paths"][path]["get"]["responses"]

        assert "401" in responses, path
        content = responses["401"]["content"]
        assert PROBLEM_MEDIA in content, path
        assert content[PROBLEM_MEDIA]["schema"]["$ref"].endswith("/ProblemDetail"), path

    assert "ProblemDetail" in document["components"]["schemas"]


def test_an_application_that_carries_no_settings_is_refused_not_asserted() -> None:
    """`assert` disappears under `python -O`; the dependency raises instead.

    An application without `app.state.settings` was not built by `create_app`, and reading
    the token off whatever is there would be worse than failing.
    """
    app = FastAPI()
    install_error_handlers(app)
    app.state.settings = "not a Settings object"

    @app.get("/needs-settings")
    def needs_settings(_: Annotated[None, Depends(require_bearer)]) -> None:
        return None

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)

    async def call() -> httpx.Response:
        async with httpx.AsyncClient(transport=transport, base_url="http://x") as client:
            return await client.get("/needs-settings")

    response = asyncio.run(call())

    assert response.status_code == HTTP_SERVER_ERROR
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA)


def test_the_token_is_compared_with_compare_digest_and_never_with_equality() -> None:
    """`==` short-circuits on the first differing byte, which is a timing oracle."""
    tree = ast.parse(inspect.getsource(deps))

    called = {
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "compare_digest" in called

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        rendered = ast.unparse(node)
        assert "token" not in rendered, f"the token is compared directly: {rendered}"
        assert "credentials" not in rendered, f"the credential is compared directly: {rendered}"


def test_the_comparison_is_over_bytes() -> None:
    """A non-ASCII `str` would make `compare_digest` raise, and the 401 would be a 500."""
    tree = ast.parse(inspect.getsource(deps))

    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "compare_digest":
            for argument in node.args:
                assert getattr(argument.func, "attr", "") == "encode", ast.unparse(argument)
            return
    pytest.fail("compare_digest is not called")
