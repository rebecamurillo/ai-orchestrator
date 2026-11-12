"""The five setup tools: projects and repositories over `/mcp` (AD-34, story 1).

What is proved here is that each tool reaches its own REST route with the bearer, and that a
variable's value never comes back over MCP (AC-17) — the answer is the API's masked form.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from orchestrator.api.providers import project_ports
from orchestrator.api.providers_trajectories import trajectory_repository
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.infrastructure.mcp import build_tools
from orchestrator.infrastructure.mcp.client import InProcessApi
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.test_mcp_endpoint import Api, Recorder, a_run, rpc, tool_text

ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
SECRET_ONE = "s3cr3t-value-one"
SECRET_TWO = "s3cr3t-value-two"

SETUP_CALLS = [
    ("create_project", {"body": {"name": "x"}}, ("POST", "/api/v1/projects", "")),
    ("update_project", {"project_id": ID, "body": {}}, ("PUT", f"/api/v1/projects/{ID}", "")),
    (
        "add_repository",
        {"project_id": ID, "body": {}},
        ("POST", f"/api/v1/projects/{ID}/repositories", ""),
    ),
    ("check_clone", {"repository_id": ID}, ("POST", f"/api/v1/repositories/{ID}/clone-check", "")),
    ("init_repository", {"repository_id": ID}, ("POST", f"/api/v1/repositories/{ID}/init", "")),
    (
        "init_repository",
        {"repository_id": ID, "body": {"harness": "claude"}},
        ("POST", f"/api/v1/repositories/{ID}/init", ""),
    ),
]


@pytest.mark.parametrize(("name", "arguments", "expected"), SETUP_CALLS, ids=str)
async def test_a_setup_tool_reaches_its_route_with_the_bearer(
    name: str, arguments: dict[str, Any], expected: tuple[str, str, str]
) -> None:
    recorder = Recorder()
    tools = {tool.__name__: tool for tool in build_tools(InProcessApi(recorder, lambda: "tok"))}

    await tools[name](**arguments)

    assert recorder.calls == [expected]
    assert recorder.authorization == ["Bearer tok"]


def test_the_update_tool_states_the_replace_and_secret_rules() -> None:
    tools = {tool.__name__: tool for tool in build_tools(InProcessApi(object(), lambda: "t"))}
    rule = (tools["update_project"].__doc__ or "").lower()

    for phrase in ("replaces", "list_projects", "masked", "without `value`", "never read back"):
        assert phrase in rule, phrase


class Setup(Api):
    """The MCP application with the project ports faked, as the REST route tests do."""

    def __init__(self, env: dict[str, str]) -> None:
        super().__init__(env, a_run())
        self.uow = FakeUnitOfWork()
        self.app.dependency_overrides[project_ports] = self._ports
        self.app.dependency_overrides[trajectory_repository] = lambda: None
        self.clock = FakeClock()
        self.projects = FakeProjectRepository()
        self.crypto = FakeCrypto()
        self.repositories = FakeRepositoryRepository()

    def _ports(self) -> ProjectPorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            repositories=self.repositories,
            crypto=self.crypto,
            clock=self.clock,
        )


async def test_a_variable_set_over_mcp_is_read_back_masked_and_never_as_a_value(
    env: dict[str, str],
) -> None:
    api = Setup(env)
    async with api.serving() as client:
        created = tool_text(
            await rpc(
                client,
                "tools/call",
                {
                    "name": "create_project",
                    "arguments": {
                        "body": {
                            "name": "Over MCP",
                            "context_text": "",
                            "context_paths": [],
                            "env_vars": [
                                {"name": "ONE", "value": SECRET_ONE},
                                {"name": "TWO", "value": SECRET_TWO},
                            ],
                        }
                    },
                },
            )
        )
        updated = await rpc(
            client,
            "tools/call",
            {
                "name": "update_project",
                "arguments": {
                    "project_id": created["id"],
                    "body": {
                        "name": "Over MCP",
                        "context_text": "",
                        "context_paths": [],
                        "env_vars": [{"name": "ONE"}, {"name": "TWO", "value": "replaced-v"}],
                    },
                },
            },
        )
        listed = await rpc(client, "tools/call", {"name": "list_projects", "arguments": {}})

    assert tool_text(updated)["id"] == created["id"]
    text = listed["result"]["content"][0]["text"]
    project = next(p for p in json.loads(text)["items"] if p["id"] == created["id"])
    assert [v["name"] for v in project["env_vars"]] == ["ONE", "TWO"]
    assert all("masked" in v and "value" not in v for v in project["env_vars"])
    for sent in (SECRET_ONE, SECRET_TWO, "replaced-v"):
        assert sent not in text
        assert sent not in json.dumps(updated)
