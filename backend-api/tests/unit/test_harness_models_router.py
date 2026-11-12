"""`GET /api/v1/harnesses/{name}/models` — router tests (epic 2 story 4)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers_harness_models import ModelSources, model_sources
from orchestrator.api.routers import (
    harness_models as router_module,  # noqa: F401 — satisfies test_check_test_pairs.py
)
from orchestrator.domain.ports.gateway import GatewayUnreachable
from orchestrator.infrastructure.gateway import LiteLLMModels
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.gateway import FakeGatewayModels

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503
KNOWN = frozenset({"claude", "codex", "local"})


class Api:
    def __init__(self, env: dict[str, str], overrides: bool = True) -> None:
        settings = Settings(**{k.lower(): v for k, v in env.items()})
        self.app: FastAPI = create_app(settings)
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.fake = FakeGatewayModels(("claude-sonnet", "gpt-5"))
        self.gateway: Any = self.fake
        self.local: tuple[str, ...] = ("local-coder", "local-general")
        if overrides:
            self.app.dependency_overrides[model_sources] = lambda: ModelSources(
                self.gateway, self.local, KNOWN
            )

    def client(self, bearer: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if bearer else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def get(api: Api, name: str, bearer: bool = True) -> httpx.Response:
    async with api.client(bearer) as client:
        return await client.get(f"/api/v1/harnesses/{name}/models")


async def test_litellm(api: Api) -> None:
    response = await get(api, "claude")
    assert response.status_code == HTTP_OK
    assert response.json() == {
        "harness": "claude",
        "source": "litellm",
        "models": ["claude-sonnet", "gpt-5"],
        "note": "the models this instance's LiteLLM key may use",
        "code": None,
        "guide": None,
    }


async def test_none_names_codex(api: Api) -> None:
    api.gateway = None
    body = (await get(api, "codex")).json()
    assert body["source"] == "none"
    assert body["models"] == []
    assert body["note"].startswith("codex cannot list its models here")
    assert body["code"] == "refusal-models-unlisted"
    assert body["guide"] == "errors/refusal-models-unlisted"


async def test_local_is_configured(api: Api) -> None:
    body = (await get(api, "local")).json()
    assert (body["source"], body["models"], body["note"]) == (
        "configured",
        ["local-coder", "local-general"],
        None,
    )
    assert api.fake.calls == 0


async def test_an_unreachable_gateway_is_a_503_problem(api: Api) -> None:
    api.gateway = FakeGatewayModels(error=GatewayUnreachable("down"))
    response = await get(api, "claude")
    assert response.status_code == HTTP_UNAVAILABLE
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "refusal-models-gateway-unreachable"
    assert body["guide"] == "errors/refusal-models-gateway-unreachable"


async def test_an_unknown_harness_is_404(api: Api) -> None:
    assert (await get(api, "nosuch")).status_code == HTTP_NOT_FOUND


async def test_the_bearer_is_required(api: Api) -> None:
    assert (await get(api, "claude", bearer=False)).status_code == HTTP_UNAUTHORIZED


async def test_without_override_a_blank_gateway_is_none(env: dict[str, str]) -> None:
    api = Api({**env, "LITELLM_BASE_URL": ""}, overrides=False)
    body = (await get(api, "claude")).json()
    assert body["source"] == "none"


def test_the_provider_keeps_one_gateway_per_application(env: dict[str, str]) -> None:
    settings = Settings(
        **{**{k.lower(): v for k, v in env.items()}, "litellm_base_url": "http://gw:4000"}
    )
    app = create_app(settings)
    request: Any = SimpleNamespace(app=app)
    app.state.settings = settings
    first = model_sources(request)
    second = model_sources(request)
    assert isinstance(first.gateway_models, LiteLLMModels)
    assert first.gateway_models is second.gateway_models
