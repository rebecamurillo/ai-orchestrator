"""The package page and its two pointer pages against the running stack (initiative
orchestrator-initiative-steps, epic 9 story 4: SPEC CAP-4; AD-39 "The guide", AD-32 amended B12).

The unit suite proves the source files' structure. What only the running stack settles is that
the image's guide build serves `initiatives/package` and the two pointer pages, that the pointer
resolves, and that every route and MCP tool the package page names is one this instance serves
(a client writes its package from the guide alone, FR-27).

Structure only (member hard rule 6): headings, line counts, page ids, routes and tool names.
"""

from __future__ import annotations

import re

import httpx
import pytest

from tests.e2e.test_guide import LLMS, _front_matter, _sections
from tests.e2e.test_mcp_setup_path import Mcp

HTTP_OK = 200
PACKAGE = "initiatives/package"
POINTERS = ("initiatives/spec", "initiatives/chain")
POINTER_MAX_LINES = 10
API_PREFIX = "/api/v1"

PACKAGE_HEADINGS = [
    "package.yaml",
    "Template type",
    "The conversation kind",
    "The step file and its words",
    "The gate",
    "The status map",
    "Install without a screen",
    "Reopen",
    "Upgrades",
]

ROUTE = re.compile(r"`(GET|PUT|POST|DELETE) (/[^\s`]+)")
#: The paragraph naming the MCP tools, and a tool name in it. A tool is named after its function
#: in `infrastructure/mcp/`, not its operation id (release review 2026-11-26).
MCP_PARAGRAPH = re.compile(r"^Each has an MCP tool:(.*?)(?:\n\n|\Z)", re.MULTILINE | re.DOTALL)
TOOL_NAME = re.compile(r"`([a-z0-9_]+)`")
PLACEHOLDER = re.compile(r"\{[^}]+\}")


def _page(client: httpx.Client, page_id: str) -> str:
    response = client.get(f"/guide/{page_id}.md")
    assert response.status_code == HTTP_OK, f"{page_id}: {response.text}"
    return response.text


def _body(text: str) -> list[str]:
    lines = text.splitlines()
    end = lines.index("---", 1)
    return [line for line in lines[end + 1 :] if line.strip()]


def _normalised(path: str) -> str:
    full = path if path.startswith(API_PREFIX) else API_PREFIX + path
    return PLACEHOLDER.sub("{}", full)


@pytest.fixture(scope="module")
def package_page(stack: str) -> str:
    with httpx.Client(base_url=stack, timeout=10.0) as client:
        return _page(client, PACKAGE)


def test_the_index_lists_the_package_page_beside_the_two_pointer_pages(stack: str) -> None:
    with httpx.Client(base_url=stack, timeout=10.0) as client:
        response = client.get(LLMS)
    assert response.status_code == HTTP_OK, response.text

    guide = _sections(response.text)["Guide"]

    assert {PACKAGE, *POINTERS} <= set(guide), guide


def test_the_package_page_is_an_open_page_with_its_nine_sections_in_order(
    package_page: str,
) -> None:
    meta = _front_matter(package_page)
    assert meta["kind"] == "page"
    assert meta["audience"] == "any"

    headings = [line[3:] for line in package_page.splitlines() if line.startswith("## ")]

    assert headings == PACKAGE_HEADINGS


def test_each_pointer_page_is_short_and_points_at_a_served_package_page(
    client: httpx.Client,
) -> None:
    for page_id in POINTERS:
        text = _page(client, page_id)
        body = _body(text)

        assert len(body) <= POINTER_MAX_LINES, (page_id, body)
        assert any(PACKAGE in line for line in body), page_id
        assert _front_matter(text)["title"], page_id

    _page(client, PACKAGE)


def test_every_route_the_package_page_names_is_served_by_this_instance(
    package_page: str, authenticated: httpx.Client
) -> None:
    response = authenticated.get("/openapi.json")
    assert response.status_code == HTTP_OK, response.text
    served = {
        (method.upper(), _normalised(path))
        for path, operations in response.json()["paths"].items()
        for method in operations
    }

    named = {(method, _normalised(path)) for method, path in ROUTE.findall(package_page)}

    assert named, "the package page names no route"
    assert named <= served, sorted(named - served)


def test_every_mcp_tool_the_package_page_names_is_listed_and_reopen_has_none(
    package_page: str, authenticated: httpx.Client
) -> None:
    tools = Mcp(authenticated)._post("tools/list", {})["result"]["tools"]
    listed = {tool["name"] for tool in tools}

    paragraph = MCP_PARAGRAPH.search(package_page)
    assert paragraph, "the package page has no MCP tool paragraph"
    named = set(TOOL_NAME.findall(paragraph.group(1)))

    assert named, "the package page names no MCP tool"
    assert named <= listed, sorted(named - listed)
    assert not {name for name in listed if "reopen" in name}
