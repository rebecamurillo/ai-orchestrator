"""`template_ports` puts the filesystem folders, rooted at the settings, on `TemplatePorts`
(story 4, AD-26)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI

from orchestrator.api.providers import SESSION_FACTORY, SETTINGS, template_ports
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.infrastructure.templates_loader import FilesystemTemplateFolders

OK = 200


class Session:
    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


async def test_the_ports_carry_the_filesystem_folders_rooted_at_the_settings(
    tmp_path: Path,
) -> None:
    (tmp_path / "shipped").mkdir()
    (tmp_path / "shipped" / "one.yaml").write_text("name: one\n")
    app = FastAPI()
    setattr(app.state, SESSION_FACTORY, Session)
    setattr(
        app.state,
        SETTINGS,
        SimpleNamespace(
            templates_dir=tmp_path / "shipped", operator_templates_dir=tmp_path / "ops"
        ),
    )
    captured: list[TemplatePorts] = []

    @app.get("/probe")
    def probe(ports: Annotated[TemplatePorts, Depends(template_ports)]) -> dict[str, Any]:
        captured.append(ports)
        return {}

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://backend-api") as client:
        assert (await client.get("/probe")).status_code == OK

    (ports,) = captured
    assert isinstance(ports.folders, FilesystemTemplateFolders)
    assert ports.folders.shipped_names() == {"one"}
    assert ports.folders.operator().state == "missing"
    assert ports.folders.operator().path == str(tmp_path / "ops")
