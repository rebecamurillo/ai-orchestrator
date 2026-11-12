"""The setup path over `POST /mcp` (AD-34, epic 2 story 1): a Project, a Repository, the clone
check, the init Run, a variable, pre-flight and a Run — every step a tool call, none a
hand-written REST request.

Runs only in `ci.yml`'s `e2e-api` job. The init Run uses the suite's own template stored under
`INIT_TEMPLATE`'s name (as `test_repository_init.py` does), never a shipped one.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.templates import E2E_INIT_TEMPLATE, REPO_INIT, ensure_named
from tests.e2e.test_clone_check import Fixtures
from tests.e2e.test_run_creation import BRANCH, save_template

MCP = "/mcp"
SECRET = "e2e-secret-value"
HEADERS = {"Accept": "application/json, text/event-stream"}


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


class Mcp:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.counter = 1
        self._post(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "1"},
            },
        )

    def _post(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self.counter += 1
        response = self.client.post(
            MCP,
            headers=HEADERS,
            json={"jsonrpc": "2.0", "id": self.counter, "method": method, "params": params},
        )
        assert response.status_code == httpx.codes.OK, response.text
        body: dict[str, Any] = response.json()
        return body

    def call(self, name: str, **arguments: Any) -> Any:
        result = self._post("tools/call", {"name": name, "arguments": arguments})["result"]
        assert result["isError"] is False, result
        return json.loads(result["content"][0]["text"])


def test_a_target_is_set_up_and_a_run_created_through_mcp_tools_alone(
    authenticated: httpx.Client, fixtures: Fixtures
) -> None:
    ensure_named(authenticated, REPO_INIT, E2E_INIT_TEMPLATE)
    leaf = f"e2e-leaf-{uuid4().hex}"
    save_template(authenticated, leaf)
    mcp = Mcp(authenticated)

    project = mcp.call("create_project", body={"name": f"e2e mcp setup {uuid4()}"})
    repository = mcp.call(
        "add_repository",
        project_id=project["id"],
        body={"url": fixtures.make(), "default_branch": BRANCH},
    )
    check = mcp.call("check_clone", repository_id=repository["id"])
    assert check["status"] == "ok", check
    init = mcp.call("init_repository", repository_id=repository["id"], body={"harness": "fake"})
    assert init["run"]["id"]

    mcp.call(
        "update_project",
        project_id=project["id"],
        body={
            "name": project["name"],
            "context_text": project["context_text"],
            "context_paths": project["context_paths"],
            "env_vars": [{"name": "E2E_VAR", "value": SECRET}],
        },
    )
    listed = mcp.call("list_projects")
    read = next(p for p in listed["items"] if p["id"] == project["id"])
    assert [v["name"] for v in read["env_vars"]] == ["E2E_VAR"]
    assert SECRET not in json.dumps(listed)

    payload = {
        "template_name": leaf,
        "template_version": 1,
        "project_id": project["id"],
        "repository_id": repository["id"],
        "base_branch": BRANCH,
        "budget_usd": "5",
    }
    mcp.call("preflight_run", body=payload)
    # The repo-init Run is parked on its own branch, so pre-flight warns and asks for consent.
    created = mcp.call("create_run", body={**payload, "conflict_consent": True})
    assert created["run"]["id"]
