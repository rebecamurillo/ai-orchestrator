"""The frozen bootstrap contract (C1): the names an installed bootstrap depends on.

Story 1, orchestrator-instance-guide epic 3 (SPEC CAP-1; AD-33). Each assertion names the C1
element it pins; renaming or dropping one turns this module red.
"""

from __future__ import annotations

import inspect

from fastapi.routing import APIRoute

from orchestrator.api.mcp_mount import MCP_PATH
from orchestrator.api.routers import guide
from orchestrator.api.routers.version import BOOTSTRAP_CONTRACT
from orchestrator.application.findings import entry, guide_id
from orchestrator.infrastructure.mcp import InProcessApi, build_tools
from tests.unit.test_mcp_endpoint import Api, a_run, rpc, tool_text

HTTP_OK = 200
GUIDE_REFS = {"index": "/llms.txt", "page_url": "/guide/{id}.md", "resource": "guide://{id}"}


async def test_c1_mcp_is_served_at_slash_mcp(env: dict[str, str]) -> None:
    api = Api(env, a_run())

    assert MCP_PATH == "/mcp", "C1: the MCP endpoint is /mcp"
    async with api.serving() as client:
        answer = await rpc(client, "tools/list")
    assert answer["result"]["tools"], "C1: /mcp answers tools/list"


async def test_c1_tools_include_version_and_read_guide(env: dict[str, str]) -> None:
    api = Api(env, a_run())

    async with api.serving() as client:
        answer = await rpc(client, "tools/list")

    names = {tool["name"] for tool in answer["result"]["tools"]}
    assert {"version", "read_guide"} <= names, "C1: tools `version` and `read_guide`"


async def test_c1_read_guide_takes_one_optional_id(env: dict[str, str]) -> None:
    api = Api(env, a_run())

    async with api.serving() as client:
        answer = await rpc(client, "tools/list")

    schema = next(t for t in answer["result"]["tools"] if t["name"] == "read_guide")["inputSchema"]
    assert set(schema["properties"]) == {"id"}, "C1: read_guide(id?) has exactly one parameter, id"
    assert "id" not in schema.get("required", []), "C1: read_guide's id is optional"

    tools = build_tools(InProcessApi(object(), lambda: "t"))
    function = next(t for t in tools if t.__name__ == "read_guide")
    parameters = inspect.signature(function).parameters
    assert list(parameters) == ["id"], "C1: read_guide's parameter is named id"
    assert parameters["id"].default is None, "C1: read_guide's id defaults to None"


async def test_c1_version_answer_carries_the_contract_and_the_guide_addresses(
    env: dict[str, str],
) -> None:
    api = Api(env, a_run())

    async with api.serving() as client:
        answer = await rpc(client, "tools/call", {"name": "version", "arguments": {}})

    body = tool_text(answer)
    assert "app_version" in body, "C1: version answers app_version"
    assert BOOTSTRAP_CONTRACT == 1, "C1: the frozen contract number is 1"
    assert body["bootstrap_contract"] == BOOTSTRAP_CONTRACT, (
        "C1: version answers bootstrap_contract"
    )
    assert body["guide"] == GUIDE_REFS, "C1: version answers guide{index, page_url, resource}"


def test_c1_llms_txt_is_a_get_route_of_the_guide_router() -> None:
    routes = [(r.path, sorted(r.methods)) for r in guide.router.routes if isinstance(r, APIRoute)]

    assert ("/llms.txt", ["GET"]) in routes, "C1: GET /llms.txt is the guide index"


def test_the_bootstrap_contract_refusal_is_an_agent_code_with_its_page() -> None:
    found = entry("refusal-bootstrap-contract")

    assert found.area == "refusal"
    assert found.source == "agent"
    assert found.message == "this instance serves a newer bootstrap contract"
    assert guide_id("refusal-bootstrap-contract") == "errors/refusal-bootstrap-contract"
