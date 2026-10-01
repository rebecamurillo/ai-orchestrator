"""`/mcp` over an ASGI transport (agent-delivery-kit plan §4).

Three things are proved here, and each is the reason this endpoint is a route on this
application rather than a package of its own:

- the tool set is what the plan declares, and each tool carries the rule its description must
  state — an agent reads the description, so an empty one is a missing instruction;
- a tool answers from the API's *own* REST operation, through the in-process client, so no tool
  reimplements a use case: the two round-tripped here are answered by the same fakes the REST
  routes are;
- an unauthenticated `POST /mcp` is the same 401 problem document every other route sends. A
  mount is entered before routing and carries no dependency, so this is the one place the
  credential check could have been forgotten.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.mcp_mount import MCP, MCP_PATH, install_mcp, presented_token
from orchestrator.api.providers import run_read_ports
from orchestrator.api.routers.version import app_version
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.mcp import build_endpoint, build_tools
from orchestrator.infrastructure.mcp.client import ApiRefusal, InProcessApi
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"
MCP_URL = f"http://backend-api{MCP_PATH}"

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
PROJECT_ID = UUID("01960000-0000-7000-9000-00000000a0f1")
REPOSITORY_ID = UUID("01960000-0000-7000-9000-00000000a0f2")

#: The tool set §4 declares. A tool added or renamed is a kit-configuration change.
EXPECTED_TOOLS = (
    "version",
    "list_templates",
    "get_template",
    "list_projects",
    "list_queue",
    "preflight_run",
    "create_run",
    "send_signal",
    "get_run",
    "get_run_detail",
    "wait_run_events",
)

PROTOCOL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def a_run() -> Run:
    return Run(
        id=new_id(),
        project_id=PROJECT_ID,
        repository_id=REPOSITORY_ID,
        template_name="repo-init",
        template_version=1,
        status="running",
        budget_usd=Decimal("10"),
        spend_usd=Decimal("0.5"),
        inputs={"base_branch": "main"},
        created_at=NOW,
        updated_at=NOW,
    )


class Api:
    """One application with the MCP endpoint installed and the Run reads faked."""

    def __init__(self, env: dict[str, str], run: Run) -> None:
        self.app: FastAPI = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.runs = FakeRunRepository([run])
        self.app.dependency_overrides[run_read_ports] = lambda: RunReadPorts(
            runs=self.runs, steps=FakeStepRunRepository()
        )
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.endpoint = getattr(self.app.state, MCP)

    @asynccontextmanager
    async def serving(self) -> AsyncIterator[httpx.AsyncClient]:
        """A client over an application whose start-up step has run — which is what opens the
        endpoint's task group, since `install_mcp` wrapped the lifespan with it."""
        async with self.app.router.lifespan_context(self.app), self.client() as client:
            yield client

    def client(self, *, anonymous: bool = False) -> httpx.AsyncClient:
        headers = dict(PROTOCOL_HEADERS)
        if not anonymous:
            headers["Authorization"] = f"Bearer {self.token}"
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


async def rpc(client: httpx.AsyncClient, method: str, params: Any = None) -> Any:
    """One JSON-RPC call, after the handshake the protocol requires."""
    await client.post(
        MCP_PATH,
        json={
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "unit-test", "version": "1"},
            },
        },
    )
    response = await client.post(
        MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
    )
    assert response.status_code == HTTP_OK, response.text
    return response.json()


def tool_text(answer: Any) -> Any:
    """A tool answer's single text block, parsed back from the JSON the tool returned."""
    result = answer["result"]
    assert result["isError"] is False, result
    return json.loads(result["content"][0]["text"])


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, a_run())


# ── the tool set ─────────────────────────────────────────────────────────────────────────


def test_the_endpoint_publishes_exactly_the_declared_tools(env: dict[str, str]) -> None:
    api = Api(env, a_run())

    assert api.endpoint.tool_names == EXPECTED_TOOLS


def test_every_tool_carries_the_rule_its_description_states() -> None:
    """The description is what an agent reads before calling; an empty one instructs nothing."""
    tools = build_tools(InProcessApi(object(), lambda: "t"))

    for tool in tools:
        assert tool.__doc__, tool.__name__
    rules = {tool.__name__: tool.__doc__ or "" for tool in tools}
    assert "pre-flight" in rules["create_run"].lower()
    assert "budget" in rules["create_run"].lower()
    assert "admitted_signals" in rules["send_signal"]
    assert "since" in rules["wait_run_events"]


async def test_tools_list_answers_the_same_names_over_the_protocol(api: Api) -> None:
    async with api.serving() as client:
        answer = await rpc(client, "tools/list")

    assert tuple(tool["name"] for tool in answer["result"]["tools"]) == EXPECTED_TOOLS
    for tool in answer["result"]["tools"]:
        assert tool["description"], tool["name"]


# ── a tool is one REST call ──────────────────────────────────────────────────────────────


async def test_the_version_tool_answers_this_instance_s_own_version(api: Api) -> None:
    async with api.serving() as client:
        answer = await rpc(client, "tools/call", {"name": "version", "arguments": {}})

    assert tool_text(answer)["app_version"] == app_version()


async def test_the_get_run_tool_reads_the_run_the_rest_route_reads(env: dict[str, str]) -> None:
    """Same fakes, same read model: the tool calls `GET /runs/{id}`, it does not re-derive it."""
    run = a_run()
    api = Api(env, run)

    async with api.serving() as client:
        answer = await rpc(
            client, "tools/call", {"name": "get_run", "arguments": {"run_id": str(run.id)}}
        )
        direct = await client.get(f"/api/v1/runs/{run.id}")

    assert tool_text(answer) == direct.json()


async def test_a_refused_rest_call_reaches_the_agent_as_the_tool_s_error(api: Api) -> None:
    """A 404 is the API's own problem document, carried through rather than rewritten."""
    async with api.serving() as client:
        answer = await rpc(
            client, "tools/call", {"name": "get_run", "arguments": {"run_id": str(new_id())}}
        )

    result = answer["result"]
    assert result["isError"] is True
    assert "404" in result["content"][0]["text"]


# ── the credential ───────────────────────────────────────────────────────────────────────


async def test_an_unauthenticated_post_is_the_same_401_problem_as_every_route(api: Api) -> None:
    async with api.client(anonymous=True) as client:
        response = await client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "type": "about:blank",
        "title": "unauthorized",
        "status": HTTP_UNAUTHORIZED,
    }


async def test_a_wrong_token_never_reaches_the_handler(api: Api) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api.app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers={**PROTOCOL_HEADERS, "Authorization": "Bearer not-the-token"},
    ) as client:
        response = await client.post(MCP_PATH, json={"jsonrpc": "2.0", "id": 1, "method": "ping"})

    assert response.status_code == HTTP_UNAUTHORIZED


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ([], ""),
        ([(b"authorization", b"Bearer tok")], "tok"),
        ([(b"Authorization", b"bearer tok")], "tok"),
        ([(b"authorization", b"Basic tok")], ""),
        ([(b"accept", b"*/*")], ""),
    ],
)
def test_the_credential_is_read_off_the_raw_scope(headers: list[Any], expected: str) -> None:
    assert presented_token({"headers": headers}) == expected


async def test_every_other_path_passes_through_the_guard_untouched(api: Api) -> None:
    async with api.client() as client:
        response = await client.get("/healthz")

    assert response.status_code == HTTP_OK


# ── the start-up step ────────────────────────────────────────────────────────────────────


async def test_the_task_group_is_opened_by_the_application_s_own_lifespan(
    env: dict[str, str],
) -> None:
    """A mount gets no lifespan; `install_mcp` wraps the one the composition root set."""
    entered: list[str] = []

    async def inner_lifespan(app: FastAPI) -> Any:
        entered.append("inner")
        yield

    app = FastAPI(lifespan=inner_lifespan)
    app.state.settings = Settings(**{k.lower(): v for k, v in env.items()})
    install_mcp(app)

    async with app.router.lifespan_context(app):
        entered.append("serving")

    assert entered == ["inner", "serving"]


def test_the_endpoint_is_built_over_the_running_version(env: dict[str, str]) -> None:
    tools = build_tools(InProcessApi(object(), lambda: "t"))

    endpoint = build_endpoint(version="9.9.9", tools=tools)

    assert endpoint.tool_names == EXPECTED_TOOLS
    assert callable(endpoint.handler)


# ── one tool, one REST call ──────────────────────────────────────────────────────────────


class Recorder:
    """An ASGI application that answers `{}` to anything and records how it was called."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []
        self.authorization: list[str] = []

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.calls.append((scope["method"], scope["path"], scope["query_string"].decode()))
        self.authorization += [
            value.decode() for name, value in scope["headers"] if name == b"authorization"
        ]
        body = b"{}"
        await send(
            {
                "type": "http.response.start",
                "status": HTTP_OK,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


RUN = "01a06887-79ab-759b-97a0-71c32ad939c2"

#: Every tool, the arguments it takes, and the one request it must make. A tool that grew a
#: second call, or answered from anywhere but the contract, fails here.
ONE_CALL = [
    ("version", {}, ("GET", "/api/v1/version", "")),
    ("list_templates", {}, ("GET", "/api/v1/templates", "")),
    (
        "get_template",
        {"name": "repo-init", "version": 2},
        ("GET", "/api/v1/templates/repo-init/2", ""),
    ),
    ("list_projects", {}, ("GET", "/api/v1/projects", "")),
    ("list_queue", {}, ("GET", "/api/v1/queue", "")),
    (
        "preflight_run",
        {"body": {"template_name": "repo-init"}},
        ("POST", "/api/v1/runs/preflight", ""),
    ),
    ("create_run", {"body": {"budget_usd": "10"}}, ("POST", "/api/v1/runs", "")),
    (
        "send_signal",
        {"run_id": RUN, "kind": "continue"},
        ("POST", f"/api/v1/runs/{RUN}/signals", ""),
    ),
    ("get_run", {"run_id": RUN}, ("GET", f"/api/v1/runs/{RUN}", "")),
    ("get_run_detail", {"run_id": RUN}, ("GET", f"/api/v1/runs/{RUN}/detail", "")),
    ("wait_run_events", {"run_id": RUN}, ("GET", f"/api/v1/runs/{RUN}/events", "wait=30")),
    (
        "wait_run_events",
        {"run_id": RUN, "wait": 5, "since": "2026-10-01T09:00:00Z"},
        ("GET", f"/api/v1/runs/{RUN}/events", "wait=5&since=2026-10-01T09%3A00%3A00Z"),
    ),
]


@pytest.mark.parametrize(("name", "arguments", "expected"), ONE_CALL, ids=str)
async def test_a_tool_makes_exactly_that_one_call_with_the_bearer(
    name: str, arguments: dict[str, Any], expected: tuple[str, str, str]
) -> None:
    recorder = Recorder()
    tools = {tool.__name__: tool for tool in build_tools(InProcessApi(recorder, lambda: "tok"))}

    await tools[name](**arguments)

    assert recorder.calls == [expected]
    assert recorder.authorization == ["Bearer tok"]


async def test_a_body_that_is_not_json_is_carried_as_text(env: dict[str, str]) -> None:
    """A 500 is `text/plain`; the agent still gets what the server said."""

    async def plain(scope: Any, receive: Any, send: Any) -> None:
        body = b"Internal Server Error"
        await send(
            {
                "type": "http.response.start",
                "status": 500,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    tools = {tool.__name__: tool for tool in build_tools(InProcessApi(plain, lambda: "tok"))}

    with pytest.raises(ApiRefusal, match="Internal Server Error"):
        await tools["version"]()
