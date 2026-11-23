"""`type` on the template version body (story 1 of epic 3, 2026-11-23)."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.api.providers import template_ports
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

HTTP_OK = 200
HTTP_CREATED = 201
BASE = "name: leaf\nversion: 1\n"
STEPS = "steps:\n  - id: sync\n    uses: git.sync\n    gate: deterministic\n"


class Harness:
    def __init__(self, env: dict[str, str]) -> None:
        self.uow = FakeUnitOfWork()
        self.templates = FakeTemplateVersionRepository()
        self.clock = FakeClock()
        self.app = create_app(Settings(**{key.lower(): value for key, value in env.items()}))
        self.app.dependency_overrides[template_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> TemplatePorts:
        if not self.uow.calls or self.uow.calls[-1] == "exit":
            self.uow.__enter__()
        return TemplatePorts(uow=self.uow, templates=self.templates, clock=self.clock)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers={"Authorization": f"Bearer {self.token}"},
        )

    def store(self, text: str) -> None:
        self.templates.add(
            TemplateVersion(
                name="leaf", version=1, yaml=text, hash="sha", created_at=self.clock.now()
            )
        )


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (BASE + "type: interactive\n" + STEPS, "interactive"),
        (BASE + STEPS, "auto"),
        ("not: [valid\n", "auto"),
    ],
)
async def test_version_body_carries_type(api: Harness, text: str, expected: str) -> None:
    api.store(text)
    async with api.client() as client:
        response = await client.get("/api/v1/templates/leaf/1")
    assert response.status_code == HTTP_OK
    assert response.json()["type"] == expected


async def test_save_body_carries_type(api: Harness) -> None:
    async with api.client() as client:
        response = await client.post(
            "/api/v1/templates/leaf/versions", json={"yaml": BASE + "type: interactive\n" + STEPS}
        )
    assert response.status_code == HTTP_CREATED
    assert response.json()["type"] == "interactive"
