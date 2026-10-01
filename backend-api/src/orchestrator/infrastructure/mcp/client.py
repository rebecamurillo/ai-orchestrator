"""How an MCP tool reaches this API: through its own REST operations, in process.

The rule this module exists to make structural (agent-delivery-kit plan §4): **no tool
reimplements a use case.** A tool is a name, a docstring and one call to the published
contract — the same operation the skill tells an agent to curl, with the same validation, the
same problem documents and the same two status writers behind it (AD-8). Anything else would
be a second implementation of the API that drifts from the first.

`httpx.ASGITransport` calls the application object directly: no socket is opened, nothing
resolves `LOCAL_BASE_URL`, and the request carries the bearer like any other (AD-4).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from orchestrator.infrastructure.mcp.facade import ToolFailure

API_PREFIX = "/api/v1"

#: The authority the in-process transport sends. Never resolved — see the module docstring.
LOCAL_BASE_URL = "http://backend-api"

#: Longer than the longest hold `GET /runs/{id}/events` allows (30 s), so a waiting tool is
#: never cut off by its own client.
REQUEST_TIMEOUT_S = 60.0


class ApiRefusal(ToolFailure):
    """A non-2xx answer, handed to the agent with the problem document the API produced.

    The API has already said what is wrong and in which field; a tool that rewrote that would
    only make the explanation worse. A `ToolFailure` rather than a bare exception because the
    protocol distinguishes the two: an anticipated failure's message reaches the agent, a
    crash's does not.
    """

    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"the orchestrator API answered {status}: {body}")
        self.status = status
        self.body = body


class InProcessApi:
    """One REST call per method, against the application this instance is serving.

    `token` is a callable rather than a string because the application is built before its
    settings are validated — `api/mcp_mount.py` says where that constraint comes from.
    """

    def __init__(self, app: Any, token: Callable[[], str]) -> None:
        self._app = app
        self._token = token

    async def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return await self._call("GET", path, params=_present(params))

    async def post(self, path: str, body: Any = None) -> Any:
        return await self._call("POST", path, json=body)

    async def _call(self, method: str, path: str, **sent: Any) -> Any:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self._app),
            base_url=LOCAL_BASE_URL,
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=REQUEST_TIMEOUT_S,
        ) as client:
            response = await client.request(method, f"{API_PREFIX}{path}", **sent)
        if response.is_success:
            return _payload(response)
        raise ApiRefusal(response.status_code, _payload(response))


def _present(params: dict[str, Any] | None) -> dict[str, Any]:
    """Only the query parameters that were given: an omitted one is not `?since=None`."""
    return {name: value for name, value in (params or {}).items() if value is not None}


def _payload(response: httpx.Response) -> Any:
    """The body as JSON where it is JSON, as text otherwise — a 500 is `text/plain`."""
    try:
        return response.json()
    except ValueError:
        return response.text
