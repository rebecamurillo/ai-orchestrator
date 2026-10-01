"""The one module that imports the MCP SDK — the AD-6 pattern applied to `/mcp`.

`pyproject.toml` carries a forbidden contract naming this module as the only exception, so a
second `import mcp` anywhere in the package fails `make lint` (`tests/unit/test_mcp_boundary.py`
proves the contract fires). Everything above it sees the two things a composition root needs:
an ASGI handler, and the task group that handler cannot answer without.

Three settings of the SDK's app are decisions rather than defaults:

- **`streamable_http_path="/"`.** The handler is reached at `/mcp` by `api/mcp_mount.py`, which
  matches the path exactly. The SDK's own Starlette app would mount its route *under* that
  prefix and answer `POST /mcp` with a 307 to `/mcp/`, which a client configured with
  `${ORCHESTRATOR_BASE_URL}/mcp` would have to be told to follow.
- **`stateless_http=True`, `json_response=True`.** One request, one answer, no server-side
  session to resume: this endpoint's tools are each a single REST call, and a session would be
  state the orchestrator already keeps in a Run.
- **DNS-rebinding protection off.** It is a host allow-list, and this instance is reached at
  whatever host the operator configured (`ORCHESTRATOR_BASE_URL`), so an allow-list here would
  refuse every real client. The control that matters is the bearer, and `api/mcp_mount.py`
  refuses an unauthenticated call before this handler sees it (AD-4).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

#: The SDK's own class for a failure a tool *anticipated*: its message reaches the agent,
#: where anything else is a crash whose text the SDK keeps on the server. Re-exported so
#: `client.py` can raise it without importing the SDK — the contract keeps that import here.
ToolFailure = ToolError

#: What the server calls itself to a client.
SERVER_NAME = "ai-orchestrator"

#: Served to the client on `initialize`; the skill is still the floor (plan §4).
INSTRUCTIONS = (
    "The orchestrator runs BMAD dev-loop workflows against your repositories. "
    "Read version first, pre-flight before creating a Run, carry the operator's budget "
    "unchanged, and send only a Signal the Run's admitted_signals lists."
)


@dataclass(frozen=True)
class McpEndpoint:
    """The endpoint as the layers above it see it: no SDK type crosses this boundary.

    `handler` is an ASGI application. `run` opens the session manager's task group, which the
    handler needs before it can answer a single request — a mount gets no lifespan of its own,
    so the application's own start-up is where it is opened.
    """

    handler: Callable[[Any, Any, Any], Any]
    run: Callable[[], AbstractAsyncContextManager[None]]
    tool_names: tuple[str, ...]


def build_endpoint(*, version: str, tools: Sequence[Callable[..., Any]]) -> McpEndpoint:
    """One MCP server over the given tools, as an ASGI handler and its task group."""
    server = MCPServer(name=SERVER_NAME, version=version, instructions=INSTRUCTIONS)
    for tool in tools:
        server.add_tool(tool)
    # built for its side effect: the session manager is created lazily by this call, and
    # `api/mcp_mount.py` serves the manager rather than the Starlette app it returns
    server.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    manager = server.session_manager
    return McpEndpoint(
        handler=manager.handle_request,
        run=manager.run,
        tool_names=tuple(tool.__name__ for tool in tools),
    )
