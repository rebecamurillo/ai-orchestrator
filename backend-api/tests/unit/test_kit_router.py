"""`GET /api/v1/kit/install.sh` and `/kit/archive` over ASGI (agent-delivery-kit plan §1)."""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

import httpx
from fastapi.routing import APIRoute

from orchestrator.api.routers.kit import GZIP_MEDIA_TYPE, SHELL_MEDIA_TYPE, router
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
PROBLEM_MEDIA_TYPE = "application/problem+json"
INSTALL = "/api/v1/kit/install.sh"
ARCHIVE = "/api/v1/kit/archive"


def _kit(root: Path) -> Path:
    (root / "install.sh").write_text("#!/usr/bin/env bash\necho kit\n")
    (root / "manifest.json").write_text(json.dumps({"kit_version": "4.5.6"}))
    (root / "skills" / "orchestrator").mkdir(parents=True)
    (root / "skills" / "orchestrator" / "SKILL.md").write_text("# orchestrator\n")
    return root


def _client(settings: Settings, token: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(settings), raise_app_exceptions=False),
        base_url="http://backend-api",
        headers=headers,
    )


def test_the_router_declares_the_two_operations() -> None:
    routes = [route for route in router.routes if isinstance(route, APIRoute)]

    assert [(route.path, sorted(route.methods)) for route in routes] == [
        ("/kit/install.sh", ["GET"]),
        ("/kit/archive", ["GET"]),
    ]
    for route in routes:
        assert route.summary
        assert HTTP_NOT_FOUND in route.responses


async def test_the_installer_is_served_as_a_shell_script(
    env: dict[str, str], tmp_path: Path
) -> None:
    async with _client(Settings(kit_dir=_kit(tmp_path)), env["ORCHESTRATOR_TOKEN"]) as client:
        response = await client.get(INSTALL)

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith(SHELL_MEDIA_TYPE)
    assert response.text == "#!/usr/bin/env bash\necho kit\n"


async def test_the_archive_is_the_kit_named_by_its_version(
    env: dict[str, str], tmp_path: Path
) -> None:
    async with _client(Settings(kit_dir=_kit(tmp_path)), env["ORCHESTRATOR_TOKEN"]) as client:
        response = await client.get(ARCHIVE)

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"] == GZIP_MEDIA_TYPE
    assert response.headers["content-disposition"] == (
        'attachment; filename="ai-orchestrator-kit-4.5.6.tar.gz"'
    )
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as tar:
        assert set(tar.getnames()) == {
            "install.sh",
            "manifest.json",
            "skills/orchestrator/SKILL.md",
        }


async def test_an_instance_without_a_kit_answers_a_problem_not_an_empty_archive(
    env: dict[str, str], tmp_path: Path
) -> None:
    async with _client(Settings(kit_dir=tmp_path / "absent"), env["ORCHESTRATOR_TOKEN"]) as c:
        for path in (INSTALL, ARCHIVE):
            response = await c.get(path)

            assert response.status_code == HTTP_NOT_FOUND, path
            assert response.headers["content-type"] == PROBLEM_MEDIA_TYPE
            assert "KIT_DIR" in response.json()["detail"]


async def test_both_routes_are_behind_the_bearer(env: dict[str, str], tmp_path: Path) -> None:
    async with _client(Settings(kit_dir=_kit(tmp_path)), None) as client:
        for path in (INSTALL, ARCHIVE):
            assert (await client.get(path)).status_code == HTTP_UNAUTHORIZED, path
