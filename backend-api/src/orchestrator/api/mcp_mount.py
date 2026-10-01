"""`/mcp` — the MCP endpoint of this API, behind the one credential (AD-4, plan §4).

MCP is a route on this application, not a separate package: same bearer, same contract, same
release number, and nothing to install or keep in step. The tools are thin and call this API's
own REST operations in process (`infrastructure/mcp/client.py`).

Three things cannot be done the way a feature router does them, and all three live here:

- **The credential.** `/mcp` is not a FastAPI route, so it cannot carry the `require_bearer`
  dependency — a mount is entered before routing and never sees it. `McpGuard` checks the same
  token with the same comparison (`api/deps.py::token_matches`), refuses with the same problem
  document and the same `WWW-Authenticate` challenge, and only then hands the request to the
  SDK's handler. Nothing reaches the handler unauthenticated.
- **When the token is read.** At request time, off `app.state.settings`, never while the
  application is being built: `tools/export_openapi.py` builds this application from
  `Settings.model_construct()`, where no field exists to dereference.
- **The start-up step.** The session manager cannot answer a request before its task group is
  open, and a mount gets no lifespan of its own, so `install_mcp` wraps whatever lifespan the
  composition root gave the application. The wrap goes *inside* that lifespan — a migration
  that fails has to leave the process with its own exception, not with a task group's
  `ExceptionGroup` around it (`tests/unit/test_migrations.py` pins that). An application built
  without a lifespan — every unit test — still answers the 401, because the guard refuses
  before the handler is reached.

The path is matched exactly rather than mounted: Starlette's `Mount("/mcp", …)` answers
`POST /mcp` with a 307 redirect to `/mcp/`, and the client configuration this kit ships says
`${ORCHESTRATOR_BASE_URL}/mcp`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from orchestrator.api.deps import UNAUTHORIZED_HEADERS, token_matches
from orchestrator.api.errors import PROBLEM_MEDIA_TYPE, ProblemDetail
from orchestrator.infrastructure.mcp import InProcessApi, McpEndpoint, build_endpoint, build_tools

#: Where the endpoint answers. The kit's harness configuration points at this path.
MCP_PATH = "/mcp"

HTTP_UNAUTHORIZED = 401
AUTHORIZATION = b"authorization"
BEARER_PREFIX = "bearer "

#: `app.state` attribute the endpoint is stored under, so a test can open its task group.
MCP = "mcp"

#: The instance token, read when it is needed rather than when the app is built.
type Token = Callable[[], str]


def unauthorized() -> JSONResponse:
    """The same body `api/deps.py` sends: one title, no detail, always the same challenge."""
    return JSONResponse(
        status_code=HTTP_UNAUTHORIZED,
        content=ProblemDetail(title="unauthorized", status=HTTP_UNAUTHORIZED).as_body(),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=UNAUTHORIZED_HEADERS,
    )


def presented_token(scope: Any) -> str:
    """The bearer credential off a raw ASGI scope, or `""` when there is none to read."""
    for name, value in scope.get("headers", ()):
        if name.lower() != AUTHORIZATION:
            continue
        header = value.decode("latin-1")
        if header.lower().startswith(BEARER_PREFIX):
            return header[len(BEARER_PREFIX) :].strip()
        return ""
    return ""


class McpGuard:
    """Serves `MCP_PATH` behind the bearer, and passes every other request through."""

    def __init__(
        self, app: Any, *, token: Token, endpoint: McpEndpoint, path: str = MCP_PATH
    ) -> None:
        self._app = app
        self._token = token
        self._endpoint = endpoint
        self._path = path

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or scope.get("path") != self._path:
            await self._app(scope, receive, send)
            return
        if not token_matches(presented_token(scope), self._token()):
            await unauthorized()(scope, receive, send)
            return
        await self._endpoint.handler(scope, receive, send)


def instance_token(app: FastAPI) -> Token:
    """The one credential, read off the settings object `create_app` stored (AD-20)."""

    def read() -> str:
        token: str = app.state.settings.orchestrator_token.get_secret_value()
        return token

    return read


def install_mcp(app: FastAPI) -> McpEndpoint:
    """Build the endpoint, guard it, and make its task group part of start-up."""
    token = instance_token(app)
    endpoint = build_endpoint(version=app.version, tools=build_tools(InProcessApi(app, token)))
    setattr(app.state, MCP, endpoint)
    app.add_middleware(McpGuard, token=token, endpoint=endpoint)
    _open_task_group_at_startup(app, endpoint.run)
    return endpoint


def _open_task_group_at_startup(app: FastAPI, run: Callable[[], Any]) -> None:
    """Wrap the application's lifespan with the endpoint's own — see the module docstring."""
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(scoped: FastAPI) -> AsyncIterator[None]:
        async with inner(scoped), run():
            yield

    app.router.lifespan_context = lifespan
