"""The MCP endpoint adapter (agent-delivery-kit plan §4).

`facade.py` is the only module that imports the SDK, `client.py` is how a tool reaches this
API, and `tools.py` is the tool set. What a composition root needs is re-exported here.
"""

from __future__ import annotations

from orchestrator.infrastructure.mcp.client import ApiRefusal, InProcessApi
from orchestrator.infrastructure.mcp.facade import (
    McpEndpoint,
    McpPrompt,
    McpResource,
    build_endpoint,
)
from orchestrator.infrastructure.mcp.tools import PAGE_ID, build_tools, prompt_name

__all__ = [
    "PAGE_ID",
    "ApiRefusal",
    "InProcessApi",
    "McpEndpoint",
    "McpPrompt",
    "McpResource",
    "build_endpoint",
    "build_tools",
    "prompt_name",
]
