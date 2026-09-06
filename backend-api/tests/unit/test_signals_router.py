"""`POST/GET /api/v1/runs/{run_id}/signals` over an ASGI transport (SPEC CAP-9, FR-20).

`handle_signal`'s own rules are `test_handle_signal.py`'s coverage; what only a request
shows is here — the route shape, the status each operation answers with, and the brief's
own read-model AC: `GET /runs/{id}` (this path included) renders `admitted_signals` for a
parked Run.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import run_read_ports, signal_effect_ports
from orchestrator.api.routers import signals as router_module
from orchestrator.application.use_cases.create_run import RunReadPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.process import FakeProcessRunner

HTTP_OK = 200
HTTP_CONFLICT = 409
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_UNAUTHORIZED = 401

RUNS = "/api/v1/runs"
BUILD = "stories[0].build"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"


def push_rejected_world() -> World:
    return a_world(
        "needs_you",
        EPIC_PLAN,
        {"push": "error"},
        park_kind="push_rejected",
        park_path="push",
        park_reason="the remote rejected it",
    )


class Api:
    """One application, one wired `World`, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str], world: World) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.world = world
        self.app: FastAPI = create_app(self.settings)
        self.app.dependency_overrides[signal_effect_ports] = self._signal_ports
        self.app.dependency_overrides[run_read_ports] = lambda: RunReadPorts(
            runs=world.ports.runs, steps=world.ports.steps
        )
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _signal_ports(self) -> Iterator[SignalEffectPorts]:
        yield SignalEffectPorts(
            signal=self.world.signal_ports,
            git=FakeGit(),
            process=FakeProcessRunner(),
            work_dir="/work",
            read_environment=lambda _run_id: None,
        )

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env, push_rejected_world())


# ── the route shape ──────────────────────────────────────────────────────────────────────


def test_the_router_declares_exactly_the_two_operations() -> None:
    routes = [(sorted(route.methods), route.path) for route in router_module.router.routes]

    assert sorted(routes) == [
        (["GET"], "/runs/{run_id}/signals"),
        (["POST"], "/runs/{run_id}/signals"),
    ]
    for route in router_module.router.routes:
        assert route.dependencies == []


async def test_every_signals_path_has_a_get(api: Api) -> None:
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    path = f"{RUNS}/{{run_id}}/signals"
    assert "get" in document["paths"][path]
    assert "post" in document["paths"][path]


# ── POST: the kinds this epic applies ───────────────────────────────────────────────────


async def test_retry_re_queues_the_errored_row_and_resumes(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{api.world.run.id}/signals", json={"kind": "retry"})

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "running"
    assert body["admitted_signals"] == ["cancel"]
    assert api.world.status_of("push") == "queued"


async def test_continue_finishes_a_checkpoint_row(env: dict[str, str]) -> None:
    world = a_world(
        "needs_you",
        EPIC_PLAN,
        {"stories[1].after": "checkpoint"},
        park_kind="checkpoint",
        park_path="stories[1].after",
        park_reason="a done checkpoint",
    )
    api = Api(env, world)

    async with api.client() as client:
        response = await client.post(f"{RUNS}/{world.run.id}/signals", json={"kind": "continue"})

    assert response.status_code == HTTP_OK, response.text
    assert response.json()["status"] == "running"
    assert world.status_of("stories[1].after") == "done"


async def test_cancel_answers_the_cancelled_run_with_no_admitted_signals(
    env: dict[str, str],
) -> None:
    world = a_world("running", EPIC_PLAN, {})
    api = Api(env, world)

    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{world.run.id}/signals", json={"kind": "cancel", "payload": {"confirm": True}}
        )

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["admitted_signals"] == []


# ── POST: refusals ───────────────────────────────────────────────────────────────────────


async def test_a_kind_outside_this_epics_scope_is_a_409_not_available_yet(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{api.world.run.id}/signals", json={"kind": "skip_epic"}
        )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "skip_epic not available yet"


async def test_a_signal_ad13_refuses_is_a_409_with_ad13s_own_text(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{api.world.run.id}/signals", json={"kind": "answer", "payload": {"text": "x"}}
        )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert "invalid for status" in response.json()["detail"]


async def test_signalling_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(f"{RUNS}/{UNKNOWN_ID}/signals", json={"kind": "retry"})

    assert response.status_code == HTTP_NOT_FOUND, response.text


async def test_an_unknown_kind_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(
            f"{RUNS}/{api.world.run.id}/signals", json={"kind": "not-a-real-kind"}
        )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text


# ── GET: the brief's own read-model AC ──────────────────────────────────────────────────


async def test_get_renders_admitted_signals_for_a_push_rejected_park(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{api.world.run.id}/signals")

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "needs_you"
    assert body["admitted_signals"] == ["retry", "skip_epic", "cancel"]


async def test_get_an_unknown_run_is_a_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/{UNKNOWN_ID}/signals")

    assert response.status_code == HTTP_NOT_FOUND, response.text


async def test_get_a_malformed_id_is_a_422(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"{RUNS}/not-a-uuid/signals")

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
