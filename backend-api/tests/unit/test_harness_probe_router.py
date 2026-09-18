"""`GET /api/v1/harnesses/{name}/probe` — router unit tests.

Pattern follows test_harnesses_router.py: one `Api` class, one `api` fixture, async tests.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI

from orchestrator.api.providers import harness_probe_ports
from orchestrator.api.routers import (
    harness_probe as router_module,  # noqa: F401 — satisfies test_check_test_pairs.py
)
from orchestrator.application.use_cases.harness_probe import HarnessProbePorts
from orchestrator.domain.ports.harness import ProbeResult
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.harness import FakeHarness

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
PROBLEM_MEDIA_TYPE = "application/problem+json"


class Api:
    """One application, one fake harness registry, and a client that carries the bearer."""

    def __init__(self, env: dict[str, str]) -> None:
        self.settings = Settings(**{key.lower(): value for key, value in env.items()})
        self.app: FastAPI = create_app(self.settings)
        self.token = env["ORCHESTRATOR_TOKEN"]
        self._harnesses: dict[str, FakeHarness] = {}
        self.app.dependency_overrides[harness_probe_ports] = self._ports

    def seed_probe(self, name: str, result: ProbeResult) -> None:
        self._harnesses[name] = FakeHarness(name=name, probe_results=[result])

    def _ports(self) -> HarnessProbePorts:
        return HarnessProbePorts(harnesses=dict(self._harnesses))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def anonymous(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
        )


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


def _ok_result() -> ProbeResult:
    return ProbeResult(ok=True, failing_reason=None, version="2.1.258", models=["gpt-4"])


def _failing_result() -> ProbeResult:
    return ProbeResult(ok=False, failing_reason="gateway unreachable", version="2.1.258", models=[])


async def test_ok_probe_returns_200(api: Api) -> None:
    api.seed_probe("claude", _ok_result())

    async with api.client() as client:
        response = await client.get("/api/v1/harnesses/claude/probe")

    assert response.status_code == HTTP_OK


async def test_failing_probe_returns_200_with_non_null_failing_reason(api: Api) -> None:
    """A probe that found issues returns HTTP 200 with ok=false — not a 4xx/5xx."""
    api.seed_probe("claude", _failing_result())

    async with api.client() as client:
        response = await client.get("/api/v1/harnesses/claude/probe")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["ok"] is False
    assert body["failing_reason"] is not None
    assert isinstance(body["failing_reason"], str)


async def test_unknown_harness_returns_404(api: Api) -> None:
    async with api.client() as client:
        response = await client.get("/api/v1/harnesses/unknown/probe")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)


async def test_response_body_has_all_four_fields(api: Api) -> None:
    api.seed_probe("claude", _ok_result())

    async with api.client() as client:
        response = await client.get("/api/v1/harnesses/claude/probe")

    body = response.json()
    assert "ok" in body
    assert "failing_reason" in body
    assert "version" in body
    assert "models" in body


async def test_without_bearer_is_401(api: Api) -> None:
    api.seed_probe("claude", _ok_result())

    async with api.anonymous() as client:
        response = await client.get("/api/v1/harnesses/claude/probe")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
