"""`/api/v1/projects/{id}/channel` and `.../channel/test` over an ASGI transport (story 3-4).

The ports are the shared fakes, injected through `dependency_overrides`. What only a request
shows is asserted here: the statuses, the problem documents, and that no body, problem or
log line carries the bot token.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import structlog
from fastapi import FastAPI

from orchestrator.api.providers import project_ports
from orchestrator.api.providers_channel import channel_ports
from orchestrator.api.routers import project_channel as router_module
from orchestrator.application.use_cases.project_channel import ChannelPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatError
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.chat import FakeChatChannel, FakeChatChannelFactory
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.project_channel import FakeProjectChannelRepository
from tests.unit.fakes.projects import FakeProjectRepository

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
PROBLEM = "application/problem+json"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def a_project(**overrides: object) -> Project:
    fields: dict[str, object] = {
        "id": new_id(),
        "slug": "acme",
        "name": "Acme",
        "context_text": "",
        "context_paths": (),
        "env_vars_enc": (),
        "log_prompt_content": False,
        "created_at": EPOCH,
        "updated_at": EPOCH,
    }
    fields.update(overrides)
    return Project(**fields)  # type: ignore[arg-type]


class Harness:
    """One application over one set of fakes, with a client that carries the bearer."""

    def __init__(self, env: dict[str, str]) -> None:
        settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.project = a_project()
        self.builtin = a_project(slug="readiness", name="readiness", builtin=True)
        self.projects = FakeProjectRepository([self.project, self.builtin])
        self.channels = FakeProjectChannelRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.chat = FakeChatChannel(probe_handle="ops-bot")
        self.factory = FakeChatChannelFactory(self.chat)
        self.uow = FakeUnitOfWork()
        self.app: FastAPI = create_app(settings)
        self.app.dependency_overrides[channel_ports] = self._ports
        self.app.dependency_overrides[project_ports] = self._project_ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _open(self) -> None:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()

    def _ports(self) -> ChannelPorts:
        self._open()
        return ChannelPorts(
            uow=self.uow,
            projects=self.projects,
            channels=self.channels,
            crypto=self.crypto,
            clock=self.clock,
            factory=self.factory,
        )

    def _project_ports(self) -> ProjectPorts:
        self._open()
        return ProjectPorts(
            uow=self.uow, projects=self.projects, crypto=self.crypto, clock=self.clock
        )

    def url(self, project_id: UUID | str | None = None, suffix: str = "") -> str:
        return f"/api/v1/projects/{project_id or self.project.id}/channel{suffix}"

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


def a_token() -> str:
    return f"tok-{uuid4()}"


def a_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "mattermost",
        "base_url": "https://chat.example.com",
        "channel_id": "c1",
        "token": a_token(),
        "allowed_users": [{"id": "u1", "handle": "alice"}],
        "metadata_only": False,
    }
    body.update(overrides)
    return body


OFF = {
    "provider": "off",
    "base_url": None,
    "channel_id": None,
    "token_set": False,
    "allowed_users": [],
    "metadata_only": False,
}


# ── read, save, keep, off ────────────────────────────────────────────────────


async def test_a_project_with_no_channel_reads_off(api: Harness) -> None:
    async with api.client() as client:
        response = await client.get(api.url())

    assert response.status_code == HTTP_OK
    assert response.json() == OFF


async def test_a_save_answers_token_set_and_never_the_token(api: Harness) -> None:
    token = a_token()

    async with api.client() as client:
        saved = await client.put(api.url(), json=a_body(token=token))
        read = await client.get(api.url())

    assert saved.status_code == HTTP_OK
    assert saved.json()["token_set"] is True
    assert read.json() == saved.json()
    assert "token" not in saved.json()
    for response in (saved, read):
        assert token not in response.text
    stored = api.channels.get(api.project.id)
    assert stored is not None
    assert api.crypto.decrypt(stored.token_enc) == token


async def test_a_save_without_a_token_keeps_the_ciphertext(api: Harness) -> None:
    async with api.client() as client:
        await client.put(api.url(), json=a_body())
        before = api.channels.get(api.project.id)
        body = a_body(channel_id="c2")
        del body["token"]
        kept = await client.put(api.url(), json=body)

    after = api.channels.get(api.project.id)
    assert kept.status_code == HTTP_OK
    assert before is not None
    assert after is not None
    assert after.token_enc == before.token_enc
    assert after.channel_id == "c2"


async def test_a_keep_with_nothing_stored_is_a_422_naming_the_token(api: Harness) -> None:
    body = a_body()
    del body["token"]

    async with api.client() as client:
        response = await client.put(api.url(), json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"] == PROBLEM
    assert response.json()["detail"] == "token: no stored token to keep"
    assert api.channels.channels == {}


async def test_turning_off_deletes_the_row_and_is_idempotent(api: Harness) -> None:
    async with api.client() as client:
        await client.put(api.url(), json=a_body())
        first = await client.put(api.url(), json={"provider": "off"})
        second = await client.put(api.url(), json={"provider": "off"})

    assert first.status_code == second.status_code == HTTP_OK
    assert first.json() == second.json() == OFF
    assert api.channels.get(api.project.id) is None


# ── refusals ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "path"),
    [
        ({"base_url": "ftp://x"}, "body.base_url"),
        ({"channel_id": ""}, "body.channel_id"),
        ({"allowed_users": []}, "body.allowed_users"),
        (
            {"allowed_users": [{"id": "u1", "handle": "a"}, {"id": "u1", "handle": "b"}]},
            "body.allowed_users",
        ),
        ({"allowed_users": [{"id": "u1", "handle": "@a"}]}, "body.allowed_users.0.handle"),
        ({"provider": "slack"}, "body.provider"),
    ],
)
async def test_a_bad_shape_is_a_422_at_its_field_and_writes_nothing(
    api: Harness, overrides: dict[str, Any], path: str
) -> None:
    token = a_token()

    async with api.client() as client:
        response = await client.put(api.url(), json=a_body(token=token, **overrides))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert path in {error["path"] for error in response.json()["errors"]}
    assert token not in response.text
    assert api.channels.channels == {}


async def test_a_malformed_token_is_refused_without_being_echoed(api: Harness) -> None:
    token = f"tok {uuid4()}"

    async with api.client() as client:
        response = await client.put(api.url(), json=a_body(token=token))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert [error["path"] for error in response.json()["errors"]] == ["body.token"]
    assert token not in response.text
    assert token.split(" ")[1] not in response.text


@pytest.mark.parametrize("body", [a_body(), {"provider": "off"}])
async def test_a_write_to_the_builtin_project_is_a_409(api: Harness, body: dict) -> None:
    async with api.client() as client:
        response = await client.put(api.url(api.builtin.id), json=body)

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"] == PROBLEM
    assert api.channels.channels == {}
    assert api.channels.deleted == []


@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [("GET", "", None), ("PUT", "", a_body()), ("POST", "/test", None)],
)
async def test_an_unknown_project_is_a_404_on_every_route(
    api: Harness, method: str, suffix: str, body: dict | None
) -> None:
    async with api.client() as client:
        response = await client.request(method, api.url(UNKNOWN_ID, suffix), json=body)

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"] == PROBLEM
    assert api.channels.channels == {}


# ── the connection test ──────────────────────────────────────────────────────


async def test_a_probe_that_answers_is_ok(api: Harness) -> None:
    async with api.client() as client:
        await client.put(api.url(), json=a_body())
        response = await client.post(api.url(suffix="/test"))

    assert response.status_code == HTTP_OK
    assert response.json() == {"ok": True, "detail": "connected as @ops-bot"}


async def test_a_refused_probe_is_a_200_with_the_platforms_text(api: Harness) -> None:
    token = a_token()
    api.chat.fail_next(ChatError(f"401 token {token} is invalid"))

    async with api.client() as client:
        await client.put(api.url(), json=a_body(token=token))
        response = await client.post(api.url(suffix="/test"))

    assert response.status_code == HTTP_OK
    assert response.json()["ok"] is False
    assert response.json()["detail"].startswith("401 token ")
    assert token not in response.text


async def test_a_test_with_no_channel_is_a_409_and_opens_nothing(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(api.url(suffix="/test"))

    assert response.status_code == HTTP_CONFLICT
    assert response.json()["detail"] == "no channel is set"
    assert api.factory.opened == []


# ── the token in nothing else ────────────────────────────────────────────────


async def test_no_project_read_and_no_log_line_carries_the_token(api: Harness) -> None:
    token = a_token()
    api.chat.fail_next(ChatError("403 not a member"))

    with structlog.testing.capture_logs() as logs:
        async with api.client() as client:
            await client.put(api.url(), json=a_body(token=token))
            responses = [
                await client.get("/api/v1/projects"),
                await client.get(f"/api/v1/projects/{api.project.id}"),
                await client.get(api.url()),
                await client.post(api.url(suffix="/test")),
            ]

    assert [response.status_code for response in responses] == [HTTP_OK] * 4
    for response in responses:
        assert token not in response.text
    assert token not in repr(logs)
    project = api.projects.get(api.project.id)
    assert project is not None
    assert project.env_vars_enc == ()


# ── the contract ─────────────────────────────────────────────────────────────


async def test_the_router_declares_three_operations_and_their_refusals(api: Harness) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    channel = document["paths"]["/api/v1/projects/{project_id}/channel"]
    test = document["paths"]["/api/v1/projects/{project_id}/channel/test"]
    assert set(channel) == {"get", "put"}
    assert set(test) == {"post"}
    assert {"404", "422"} <= set(channel["get"]["responses"])
    assert {"404", "409", "422"} <= set(channel["put"]["responses"])
    assert {"404", "409", "422"} <= set(test["post"]["responses"])
    assert len(router_module.router.routes) == len(("get", "put", "post"))


async def test_the_contract_carries_the_token_write_only(api: Harness) -> None:
    async with api.client() as client:
        schemas = (await client.get("/openapi.json")).json()["components"]["schemas"]

    token = schemas["ChannelIn"]["properties"]["token"]
    assert "token" not in schemas["ChannelOut"]["properties"]
    assert "token_set" in schemas["ChannelOut"]["required"]
    assert "writeOnly" in repr(token)
    assert "slack" not in repr(schemas["ChannelIn"]) + repr(schemas["ChannelOut"])
