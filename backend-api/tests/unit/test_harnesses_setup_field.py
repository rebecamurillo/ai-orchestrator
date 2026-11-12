"""`setup` on every `GET /api/v1/harnesses` item (story 2, orchestrator-deploy-folder epic 1,
2026-11-11; AC1, AC3)."""

from __future__ import annotations

from pathlib import Path

import pytest
from structlog.testing import capture_logs

from orchestrator.api.providers_base import setup_record
from orchestrator.domain.entities.harness import Harness
from orchestrator.infrastructure.setup_record import RECORD
from tests.unit.fakes.setup_record import FakeSetupRecord, setup_run
from tests.unit.test_harnesses_router import HARNESSES, HTTP_OK, Api

NAMES = ("claude", "codex", "opencode", "local")


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    api = Api(env)
    for name in NAMES:
        api.harnesses.add(Harness(name=name, version_pin="1"))
    return api


async def _items(api: Api) -> list[dict[str, object]]:
    async with api.client() as client:
        response = await client.get(HARNESSES)
    assert response.status_code == HTTP_OK
    items: list[dict[str, object]] = response.json()["items"]
    return items


async def test_ac1_every_item_carries_the_failed_setup(api: Api) -> None:
    run = setup_run(
        scripts=[
            {"name": "10-copy.sh", "exit": 1, "ok": False, "clashes": [], "seconds": 1, "log": "l"}
        ]
    )
    fake = FakeSetupRecord(run)
    api.app.dependency_overrides[setup_record] = lambda: fake

    items = await _items(api)

    assert {item["name"]: item["setup"]["skills"] for item in items} == {  # type: ignore[index]
        "claude": 12,
        "codex": 9,
        "opencode": 7,
        "local": 7,
    }
    for item in items:
        setup = item["setup"]
        assert isinstance(setup, dict)
        assert setup["ok"] is False
        assert setup["failures"] == [{"script": "10-copy.sh", "reason": "exit 1"}]
        assert setup["trigger"] == "install"
        assert setup["at"] == "2026-11-11T08:00:00Z"
    assert fake.reads == 1


async def test_a_good_record_is_ok_with_no_failures(api: Api) -> None:
    api.app.dependency_overrides[setup_record] = lambda: FakeSetupRecord(setup_run())

    for item in await _items(api):
        assert item["setup"]["ok"] is True  # type: ignore[index]
        assert item["setup"]["failures"] == []  # type: ignore[index]


async def test_ac3_no_record_is_null_and_silent(api: Api, tmp_path: Path) -> None:
    api.settings = api.settings.model_copy(update={"agent_home": tmp_path})
    api.app.state.settings = api.settings

    with capture_logs() as logs:
        items = await _items(api)

    assert [item["setup"] for item in items] == [None] * 4
    assert logs == []


async def test_ac3_a_corrupt_record_is_null_with_one_warning(api: Api, tmp_path: Path) -> None:
    (tmp_path / RECORD).parent.mkdir(parents=True)
    (tmp_path / RECORD).write_text("{nope")
    api.app.state.settings = api.settings.model_copy(update={"agent_home": tmp_path})

    with capture_logs() as logs:
        items = await _items(api)

    assert [item["setup"] for item in items] == [None] * 4
    assert [log["event"] for log in logs] == ["setup record unreadable"]
