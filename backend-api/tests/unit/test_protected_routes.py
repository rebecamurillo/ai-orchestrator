"""`api/protected_routes.py`: the one place a feature router is mounted behind the bearer."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import APIRouter, FastAPI

from orchestrator.api.protected_routes import install_metrics_routes, mount_protected
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

HTTP_UNAUTHORIZED = 401
CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "openapi.json"
NEW_PATH = "/api/v1/metrics/catalogue"


async def test_mount_protected_puts_a_router_under_the_prefix_behind_the_bearer(
    env: dict[str, str],
) -> None:
    app = create_app(Settings())
    scratch = APIRouter()

    @scratch.get("/scratch")
    def scratch_route() -> dict[str, bool]:
        return {"ok": True}

    mount_protected(app, scratch)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://backend-api"
    ) as client:
        refused = await client.get("/api/v1/scratch")
        allowed = await client.get(
            "/api/v1/scratch", headers={"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"}
        )

    assert refused.status_code == HTTP_UNAUTHORIZED
    assert allowed.json() == {"ok": True}
    assert str(HTTP_UNAUTHORIZED) in app.openapi()["paths"]["/api/v1/scratch"]["get"]["responses"]


def test_install_metrics_routes_registers_the_catalogue_path() -> None:
    app = FastAPI()
    install_metrics_routes(app)
    assert NEW_PATH in app.openapi()["paths"]


def test_metrics_routes_come_before_the_guide_and_nothing_else_was_lost(
    env: dict[str, str],
) -> None:
    app = create_app(Settings())
    paths = list(app.openapi()["paths"])

    assert paths.index(NEW_PATH) < paths.index("/llms.txt")
    published = {p for p in json.loads(CONTRACT.read_text())["paths"] if p.startswith("/api/v1")}
    assert published - {NEW_PATH} <= set(paths)
