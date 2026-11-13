"""The agent connection against the running stack (initiative orchestrator-instance-guide,
epic 2: SPEC CAP-2, CAP-3, CAP-4, CAP-5; member AD-32, AD-34, AD-35).

The unit suite proves every rule over fakes and guides built in `tmp_path`. What only the
running image settles: `/mcp` refuses without the bearer and publishes the epic's tools; the
guide the image built is what `read_guide`, the `guide://{id}` resources and the procedure
prompts serve; the spec-folder check and the models answer are mounted behind the bearer and
answer the same through REST and through their tool.

The e2e stack leaves `OPERATOR_TEMPLATES_DIR` and `LITELLM_BASE_URL` to the Operator's `.env`:
the models test accepts each answer the configuration can produce and checks the shape of
whichever arrives; it never skips. No assertion reads page prose or pins which pages ship
(member hard rule 6).
"""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.mcp.tools import prompt_name

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAVAILABLE = 503

MCP = "/mcp"
MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
SPEC_FOLDERS = "/api/v1/spec-folders/validate"
TEMPLATES = "/api/v1/templates"
LLMS = "/llms.txt"

DUPLICATE = "spec-duplicate-entry-id"
UNLISTED = "refusal-models-unlisted"
UNREACHABLE = "refusal-models-gateway-unreachable"
UNAVAILABLE = "refusal-guide-unavailable"

EPIC_TOOLS = {
    "create_project",
    "update_project",
    "add_repository",
    "check_clone",
    "init_repository",
    "validate_template",
    "save_template",
    "reload_templates",
    "validate_spec_folder",
    "list_models",
    "read_guide",
}

INDEX_LINK = re.compile(r"^- \[[^\]]+\]\(/guide/(?P<id>[a-z0-9-]+(?:/[a-z0-9-]+)*)\.md\)$")

LEAF = (
    "name: {name}\nversion: 1\nsteps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"
)

STORIES = "e1/stories.yaml"


def _stories(*ids: str) -> str:
    return "".join(f'- {{id: "{i}", title: T{i}, description: d}}\n' for i in ids)


def _clean_folder() -> dict[str, str]:
    return {
        "epics.yaml": "- {id: e1, title: One, branch: feat/e1, spec_folder: e1}\n",
        STORIES: _stories("1", "2"),
        "e1/SPEC.md": "# spec\n",
        "e1/stories/1-first.md": "x",
        "e1/stories/2-second.md": "x",
    }


class Mcp:
    """JSON-RPC over `POST /mcp`, as an MCP client in JSON response mode sends it."""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.counter = 0
        self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "1"},
            },
        )

    def rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.counter += 1
        response = self.client.post(
            MCP,
            headers=MCP_HEADERS,
            json={"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params or {}},
        )
        assert response.status_code == HTTP_OK, response.text
        body = response.json()
        assert "error" not in body, body
        return body["result"]

    def text(self, tool: str, /, **arguments: Any) -> tuple[bool, str]:
        """`(isError, text)` of one tool call."""
        result = self.rpc("tools/call", {"name": tool, "arguments": arguments})
        return bool(result["isError"]), str(result["content"][0]["text"])

    def call(self, tool: str, /, **arguments: Any) -> Any:
        is_error, text = self.text(tool, **arguments)
        assert is_error is False, text
        return json.loads(text)


@pytest.fixture
def mcp(authenticated: httpx.Client) -> Mcp:
    return Mcp(authenticated)


@pytest.fixture(scope="module")
def page_ids(stack: str) -> list[str]:
    with httpx.Client(base_url=stack, timeout=10.0) as client:
        response = client.get(LLMS)
    assert response.status_code == HTTP_OK, response.text
    ids = [m["id"] for line in response.text.splitlines() if (m := INDEX_LINK.match(line))]
    assert ids, "the image's guide lists no page"
    return ids


def _kind(page: str) -> str:
    lines = page.splitlines()
    end = lines.index("---", 1)
    fields = dict(line.split(": ", 1) for line in lines[1:end])
    return fields["kind"]


# --- /mcp itself -------------------------------------------------------------------------


def test_mcp_refuses_without_the_bearer(client: httpx.Client) -> None:
    response = client.post(
        MCP,
        headers=MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response.status_code == HTTP_UNAUTHORIZED, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


def test_mcp_publishes_the_epic_tools(mcp: Mcp) -> None:
    names = {tool["name"] for tool in mcp.rpc("tools/list")["tools"]}
    assert names >= EPIC_TOOLS, EPIC_TOOLS - names


# --- CAP-5: the guide over MCP -----------------------------------------------------------


def test_read_guide_serves_the_index_and_every_page_as_the_open_routes_do(
    mcp: Mcp, client: httpx.Client, page_ids: list[str]
) -> None:
    is_error, index = mcp.text("read_guide")
    assert is_error is False, index
    assert index == client.get(LLMS).text
    for page_id in page_ids:
        is_error, text = mcp.text("read_guide", id=page_id)
        assert is_error is False, text
        assert text == client.get(f"/guide/{page_id}.md").text, page_id


def test_read_guide_refuses_an_id_that_is_not_a_page_id(mcp: Mcp) -> None:
    is_error, text = mcp.text("read_guide", id="../api/v1/projects")
    assert is_error is True
    assert "not a page id" in text


def test_read_guide_on_an_unknown_page_carries_the_refusal_code(mcp: Mcp) -> None:
    is_error, text = mcp.text("read_guide", id=f"no-such-page-{uuid4().hex}")
    assert is_error is True
    assert "404" in text
    assert UNAVAILABLE in text


def test_every_page_is_a_resource_that_reads_as_the_open_route(
    mcp: Mcp, client: httpx.Client, page_ids: list[str]
) -> None:
    listed = mcp.rpc("resources/list")["resources"]
    assert {r["uri"] for r in listed} == {f"guide://{i}" for i in page_ids}
    assert {r["mimeType"] for r in listed} == {"text/markdown"}
    for page_id in page_ids:
        contents = mcp.rpc("resources/read", {"uri": f"guide://{page_id}"})["contents"]
        assert contents[0]["text"] == client.get(f"/guide/{page_id}.md").text, page_id


def test_every_procedure_and_no_other_page_is_a_prompt(
    mcp: Mcp, client: httpx.Client, page_ids: list[str]
) -> None:
    texts = {i: client.get(f"/guide/{i}.md").text for i in page_ids}
    procedures = {i for i, text in texts.items() if _kind(text) == "procedure"}
    listed = {p["name"] for p in mcp.rpc("prompts/list")["prompts"]}
    assert listed == {prompt_name(i) for i in procedures}
    for page_id in procedures:
        messages = mcp.rpc("prompts/get", {"name": prompt_name(page_id)})["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"]["text"] == texts[page_id]


# --- CAP-3: one spec-folder check --------------------------------------------------------


def test_the_spec_folder_check_is_behind_the_bearer(client: httpx.Client) -> None:
    response = client.post(SPEC_FOLDERS, json={"files": _clean_folder()})
    assert response.status_code == HTTP_UNAUTHORIZED, response.text


def test_a_clean_spec_folder_has_no_finding(authenticated: httpx.Client) -> None:
    response = authenticated.post(SPEC_FOLDERS, json={"files": _clean_folder()})
    assert response.status_code == HTTP_OK, response.text
    assert response.json() == {"findings": []}


def test_duplicate_story_ids_are_a_finding_whose_guide_page_is_served(
    authenticated: httpx.Client, client: httpx.Client
) -> None:
    files = _clean_folder() | {STORIES: _stories("3", "3")}
    response = authenticated.post(SPEC_FOLDERS, json={"files": files})
    assert response.status_code == HTTP_OK, response.text
    (finding,) = response.json()["findings"]
    assert finding["code"] == DUPLICATE
    assert finding["guide"] == f"errors/{DUPLICATE}"
    assert finding["path"] == STORIES
    assert client.get(f"/guide/{finding['guide']}.md").status_code == HTTP_OK


@pytest.mark.parametrize("path", ["/abs/epics.yaml", "e1/../epics.yaml", "./epics.yaml", "a\\b"])
def test_an_unsafe_path_is_refused_before_any_check(authenticated: httpx.Client, path: str) -> None:
    response = authenticated.post(SPEC_FOLDERS, json={"files": {path: "- {}\n"}})
    assert response.status_code == HTTP_UNPROCESSABLE, response.text


def test_validate_spec_folder_answers_what_the_route_answers(
    mcp: Mcp, authenticated: httpx.Client
) -> None:
    files = _clean_folder() | {STORIES: _stories("3", "3")}
    over_rest = authenticated.post(SPEC_FOLDERS, json={"files": files}).json()
    assert mcp.call("validate_spec_folder", files=files) == over_rest


# --- CAP-4: the models a Run can use -----------------------------------------------------


def test_the_local_harness_answers_its_configured_models(authenticated: httpx.Client) -> None:
    response = authenticated.get("/api/v1/harnesses/local/models")
    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["harness"] == "local"
    assert body["source"] == "configured"
    assert body["code"] is None


@pytest.mark.parametrize("harness", ["claude", "codex"])
def test_a_remote_harness_names_the_source_of_its_list(
    authenticated: httpx.Client, harness: str
) -> None:
    """Whichever answer this stack's LiteLLM configuration gives, it never guesses (AD-35)."""
    response = authenticated.get(f"/api/v1/harnesses/{harness}/models")
    if response.status_code == HTTP_UNAVAILABLE:
        assert response.json()["code"] == UNREACHABLE
        return
    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["harness"] == harness
    assert body["source"] in {"litellm", "none"}
    if body["source"] == "none":
        assert body["models"] == []
        assert body["code"] == UNLISTED
        assert body["guide"] == f"errors/{UNLISTED}"
        assert harness in body["note"]
    else:
        assert body["code"] is None
        assert body["note"]


def test_an_unknown_harness_is_not_found(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"/api/v1/harnesses/no-such-{uuid4().hex[:8]}/models")
    assert response.status_code == HTTP_NOT_FOUND, response.text


def test_the_models_route_is_behind_the_bearer(client: httpx.Client) -> None:
    assert client.get("/api/v1/harnesses/claude/models").status_code == HTTP_UNAUTHORIZED


def test_list_models_answers_what_the_route_answers(mcp: Mcp, authenticated: httpx.Client) -> None:
    over_rest = authenticated.get("/api/v1/harnesses/local/models").json()
    assert mcp.call("list_models", harness="local") == over_rest


def test_list_models_refuses_a_name_that_is_not_a_harness_name(mcp: Mcp) -> None:
    is_error, _ = mcp.text("list_models", harness="../instance")
    assert is_error is True


# --- CAP-2: workflows over MCP -----------------------------------------------------------


def test_save_template_saves_a_workflow_the_folder_does_not_hold(mcp: Mcp) -> None:
    """The tool always sends `refuse_if_in_folder`; a name outside the folder still saves."""
    name = f"e2e-mcp-{uuid4().hex[:12]}"
    saved = mcp.call("save_template", name=name, yaml=LEAF.format(name=name))
    assert saved["in_folder"] is False
    listed = mcp.call("list_templates")
    assert name in {t["name"] for t in listed["items"]}


def test_a_web_save_with_the_flag_on_a_name_outside_the_folder_succeeds(
    authenticated: httpx.Client,
) -> None:
    name = f"e2e-flag-{uuid4().hex[:12]}"
    response = authenticated.post(
        f"{TEMPLATES}/{name}/versions",
        json={"yaml": LEAF.format(name=name), "refuse_if_in_folder": True},
    )
    assert response.status_code == HTTP_CREATED, response.text
    assert response.json()["in_folder"] is False


def test_validate_template_findings_carry_a_served_guide_page(
    mcp: Mcp, client: httpx.Client
) -> None:
    name = f"e2e-bad-{uuid4().hex[:12]}"
    answer = mcp.call("validate_template", name=name, yaml=LEAF.format(name=name) + "bogus: 1\n")
    assert answer["errors"], answer
    for finding in answer["errors"]:
        assert finding["code"]
        assert isinstance(finding["line"], int)
        assert client.get(f"/guide/{finding['guide']}.md").status_code == HTTP_OK


@pytest.mark.parametrize("name", ["a/b", "a?b", "..", "a%2fb"])
def test_a_workflow_name_that_could_leave_its_route_is_refused(mcp: Mcp, name: str) -> None:
    is_error, _ = mcp.text("save_template", name=name, yaml=LEAF.format(name="x"))
    assert is_error is True
