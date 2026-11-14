"""`GET /runs/{id}/analysis/{analysis}/findings` and the new analysis fields (story 4, AC8)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from orchestrator.api.providers_metrics import analysis_read_ports
from orchestrator.api.routers import run_findings as router_module
from orchestrator.api.schemas.run_analyses import RunAnalysesOut
from orchestrator.api.schemas.run_findings import FindingsOut
from orchestrator.application.analysis.findings import FINDINGS_TOOL
from orchestrator.application.use_cases.analysis_findings import FindingRow
from orchestrator.application.use_cases.analysis_sarif import AnalysisReadPorts
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.db import FakeUnitOfWork

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
PROBLEM = "application/problem+json"
ROW = {
    "kind": "bug",
    "rule": "r.bug",
    "path": "a.py",
    "line": None,
    "severity": "low",
    "cwe": [],
    "state": "new",
}


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.run_id = new_id()
        self.analyses = FakeAnalysisRepository()
        self.found = Analysis(
            id=new_id(),
            run_id=self.run_id,
            repository_path=".",
            status="ok",
            created_at=datetime(2026, 11, 13, tzinfo=UTC),
        )
        self.analyses.add(self.found)
        self.analyses.add_artifact(
            AnalysisArtifact(
                id=new_id(),
                analysis_id=self.found.id,
                tool=FINDINGS_TOOL,
                media_type="application/json",
                body=json.dumps([ROW]).encode(),
            )
        )
        self.app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[analysis_read_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> Iterator[AnalysisReadPorts]:
        yield AnalysisReadPorts(self.analyses, FakeUnitOfWork())

    def client(self, *, auth: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if auth else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )

    def url(self, analysis_id: object | None = None) -> str:
        return f"/api/v1/runs/{self.run_id}/analysis/{analysis_id or self.found.id}/findings"


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_the_listing_is_answered(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url())

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["analysis_id"] == str(api.found.id)
    assert body["items"] == [ROW]


async def test_an_unknown_analysis_is_404_problem_json(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(api.url(new_id()))

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_missing_bearer_is_401(api: Api) -> None:
    async with api.client(auth=False) as client:
        assert (await client.get(api.url())).status_code == HTTP_UNAUTHORIZED


def test_the_schema_maps_rows() -> None:
    out = FindingsOut.of(new_id(), [FindingRow("bug", "r", "p", None, "low", (), "new")])

    assert out.items[0].cwe == []
    assert out.items[0].line is None


def test_the_route_declares_its_problem_answers() -> None:
    [route] = router_module.router.routes

    assert {HTTP_NOT_FOUND, 422} <= set(route.responses)  # type: ignore[attr-defined]


def test_the_analyses_schema_carries_the_new_fields() -> None:
    from tests.unit.application.test_run_analyses import World  # noqa: PLC0415

    world = World()
    found = world.analysis(".")
    world.version(1, found)
    from orchestrator.application.use_cases.run_analyses import run_analyses  # noqa: PLC0415

    out = RunAnalysesOut.of(run_analyses(world.ports, world.run.id, 1))

    assert out.step_entries == []
    assert out.items[0].rule_pack_hash is None
