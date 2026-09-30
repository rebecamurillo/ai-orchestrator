"""`GET /api/v1/version` over ASGI — the handshake's other half (agent-delivery-kit plan §3)."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import httpx
import pytest
from fastapi.routing import APIRoute

from orchestrator.api.routers import version as router_module
from orchestrator.api.routers.version import SOURCE_VERSION, VersionOut, app_version, router
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.conftest import REPO_ROOT

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
VERSION = "/api/v1/version"


def _client(settings: Settings, token: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings), raise_app_exceptions=False),
        base_url="http://backend-api",
        headers=headers,
    )


def test_the_router_declares_one_operation_with_its_model() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]

    assert [(route.path, sorted(route.methods)) for route in routes] == [("/version", ["GET"])]
    assert routes[0].response_model is VersionOut
    assert routes[0].summary


def test_the_app_version_is_the_version_file_as_spelled() -> None:
    """Not the distribution's: PEP 440 would turn `1.0.0-beta` into `1.0.0b0`."""
    assert app_version() == (REPO_ROOT / "VERSION").read_text().strip()


def test_without_the_file_the_installed_distribution_answers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(router_module, "VERSION_FILE", tmp_path / "absent")

    assert app_version() == version("orchestrator")


def test_an_uninstalled_source_tree_reports_the_marker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def missing(_name: str) -> str:
        raise PackageNotFoundError("orchestrator")

    monkeypatch.setattr(router_module, "VERSION_FILE", tmp_path / "absent")
    monkeypatch.setattr(router_module, "metadata_version", missing)

    assert app_version() == SOURCE_VERSION


async def test_the_payload_names_the_app_the_kit_bmad_and_every_harness(
    env: dict[str, str], tmp_path: Path
) -> None:
    (tmp_path / "manifest.json").write_text(json.dumps({"kit_version": "9.9.9"}))
    settings = Settings(kit_dir=tmp_path)

    async with _client(settings, env["ORCHESTRATOR_TOKEN"]) as client:
        response = await client.get(VERSION)

    assert response.status_code == HTTP_OK
    assert response.json() == {
        "app_version": (REPO_ROOT / "VERSION").read_text().strip(),
        "kit_version": "9.9.9",
        "bmad_version": env["BMAD_VERSION"],
        "harness_versions": {
            "claude": env["CLAUDE_CODE_VERSION"],
            "codex": env["CODEX_VERSION"],
            "opencode": env["OPENCODE_VERSION"],
        },
    }


async def test_an_instance_without_a_kit_reports_a_null_kit_version(
    env: dict[str, str], tmp_path: Path
) -> None:
    async with _client(Settings(kit_dir=tmp_path / "absent"), env["ORCHESTRATOR_TOKEN"]) as c:
        response = await c.get(VERSION)

    assert response.status_code == HTTP_OK
    assert response.json()["kit_version"] is None


async def test_the_route_is_behind_the_bearer(env: dict[str, str]) -> None:
    async with _client(Settings(), None) as client:
        response = await client.get(VERSION)

    assert response.status_code == HTTP_UNAUTHORIZED
