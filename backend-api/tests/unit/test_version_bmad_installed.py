"""`bmad_installed` on `GET /api/v1/version` (story 2, orchestrator-deploy-folder epic 1,
2026-11-11; AC3, AC4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from structlog.testing import capture_logs

from orchestrator.api.providers_base import setup_record
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.setup_record import RECORD
from orchestrator.main import create_app
from tests.unit.fakes.setup_record import FakeSetupRecord, setup_run

VERSION = "/api/v1/version"


async def _get(env: dict[str, str], settings: Settings, override: Any = None) -> dict[str, Any]:
    app = create_app(settings)
    if override is not None:
        app.dependency_overrides[setup_record] = lambda: override
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://backend-api",
        headers={"Authorization": f"Bearer {env['ORCHESTRATOR_TOKEN']}"},
    ) as client:
        response = await client.get(VERSION)
    assert response.status_code == 200  # noqa: PLR2004
    body: dict[str, Any] = response.json()
    return body


async def test_ac4_an_installed_ok_record_names_its_version(
    env: dict[str, str], tmp_path: Path
) -> None:
    body = await _get(env, Settings(agent_home=tmp_path), FakeSetupRecord(setup_run()))

    assert body["bmad_installed"] == "6.13.0"
    assert body["bmad_version"] == env["BMAD_VERSION"]


async def test_ac4_a_failed_or_removed_bmad_is_null(env: dict[str, str], tmp_path: Path) -> None:
    for bmad in (
        {"choice": "installed", "version": "6.13.0", "ok": False},
        {"choice": "removed", "ok": True},
    ):
        body = await _get(env, Settings(agent_home=tmp_path), FakeSetupRecord(setup_run(bmad=bmad)))
        assert body["bmad_installed"] is None


async def test_ac3_no_record_is_null_and_silent(env: dict[str, str], tmp_path: Path) -> None:
    with capture_logs() as logs:
        body = await _get(env, Settings(agent_home=tmp_path))

    assert body["bmad_installed"] is None
    assert logs == []


async def test_ac3_a_corrupt_record_is_null_with_one_warning(
    env: dict[str, str], tmp_path: Path
) -> None:
    (tmp_path / RECORD).parent.mkdir(parents=True)
    (tmp_path / RECORD).write_text("[]")

    with capture_logs() as logs:
        body = await _get(env, Settings(agent_home=tmp_path))

    assert body["bmad_installed"] is None
    assert [log["event"] for log in logs] == ["setup record unreadable"]


async def test_the_real_adapter_reads_the_file(env: dict[str, str], tmp_path: Path) -> None:
    (tmp_path / RECORD).parent.mkdir(parents=True)
    (tmp_path / RECORD).write_text(setup_run().model_dump_json())

    assert (await _get(env, Settings(agent_home=tmp_path)))["bmad_installed"] == "6.13.0"
