"""`build_guide` writes the format schemas and the open route serves them (AD-35)."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from orchestrator.api.routers import guide, version
from orchestrator.application.format_schemas import spec_folder_schema, workflow_schema
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from orchestrator.tools import build_guide

HTTP_OK = 200
FILES: list[tuple[str, Callable[[], dict[str, Any]]]] = [
    ("workflow.json", workflow_schema),
    ("spec-folder.json", spec_folder_schema),
]


@pytest.fixture
def out(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    (source / "one.md").write_text("---\ntitle: One\nkind: page\naudience: any\n---\nBody\n")
    target = tmp_path / "build"
    code = build_guide.main(
        ["--source", str(source), "--out", str(target), "--version-file", str(version.VERSION_FILE)]
    )
    assert code == 0
    return target


@pytest.mark.parametrize(("name", "make"), FILES)
def test_the_build_writes_each_schema(out: Path, name: str, make: Callable[[], Any]) -> None:
    text = (out / "schemas" / name).read_text()
    assert text.endswith("\n")
    assert text == json.dumps(make(), indent=2, sort_keys=True) + "\n"


def test_schemas_are_not_indexed(out: Path) -> None:
    pages = json.loads((out / "guide-index.json").read_text())["pages"]
    assert not [page for page in pages if page["id"].startswith("schemas")]


@pytest.mark.parametrize(("name", "make"), FILES)
async def test_the_route_serves_each_schema_without_a_bearer(
    env: dict[str, str], out: Path, name: str, make: Callable[[], Any]
) -> None:
    app = create_app(Settings())
    app.dependency_overrides[guide.guide_dir] = lambda: out
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        response = await client.get(f"/schemas/{name}")
    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith("application/schema+json")
    assert json.loads(response.text) == make()
