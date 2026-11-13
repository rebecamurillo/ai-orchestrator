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

from collections.abc import Awaitable, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.mcpserver.prompts import Prompt
from mcp.server.mcpserver.prompts.base import UserMessage
from mcp.server.mcpserver.resources.types import FunctionResource
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
    "unchanged, and send only a Signal the Run's admitted_signals lists. "
    "Read the guide: read_guide with no id lists every page."
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


@dataclass(frozen=True)
class McpResource:
    """A readable document the endpoint lists under `uri`; `read` returns its text."""

    uri: str
    name: str
    description: str
    mime_type: str
    read: Callable[[], Awaitable[str]]


@dataclass(frozen=True)
class McpPrompt:
    """A named prompt whose single user message is the text `render` returns."""

    name: str
    description: str
    render: Callable[[], Awaitable[str]]


def _user_message(render: Callable[[], Awaitable[str]]) -> Callable[[], Awaitable[UserMessage]]:
    async def message() -> UserMessage:
        return UserMessage(await render())

    return message


def build_endpoint(
    *,
    version: str,
    tools: Sequence[Callable[..., Any]],
    resources: Sequence[McpResource] = (),
    prompts: Sequence[McpPrompt] = (),
) -> McpEndpoint:
    """One MCP server over the given tools, resources and prompts, as an ASGI handler."""
    server = MCPServer(name=SERVER_NAME, version=version, instructions=INSTRUCTIONS)
    for tool in tools:
        server.add_tool(tool)
    for resource in resources:
        server.add_resource(
            FunctionResource(
                uri=resource.uri,  # type: ignore[arg-type]
                name=resource.name,
                description=resource.description,
                mime_type=resource.mime_type,
                fn=resource.read,
            )
        )
    for prompt in prompts:
        server.add_prompt(
            Prompt.from_function(
                _user_message(prompt.render), name=prompt.name, description=prompt.description
            )
        )
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
