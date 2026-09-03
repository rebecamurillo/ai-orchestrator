"""The one route this story ships, and the contract document FastAPI derives from it."""

from __future__ import annotations

from importlib.metadata import version

import httpx

from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

HTTP_OK = 200


async def _get(path: str) -> httpx.Response:
    app = create_app(Settings())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        return await client.get(path)


async def test_healthz_reports_ok_and_the_package_version(env: dict[str, str]) -> None:
    response = await _get("/healthz")

    assert response.status_code == HTTP_OK
    assert response.json() == {"status": "ok", "version": version("orchestrator")}


async def test_openapi_document_is_served_and_describes_healthz(env: dict[str, str]) -> None:
    response = await _get("/openapi.json")

    assert response.status_code == HTTP_OK
    assert "/healthz" in response.json()["paths"]
