"""`GET /runs/{id}/analysis/{analysis_id}/sarif/{tool}` over fakes (epic 5 story 4, AC6)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from orchestrator.api.providers_metrics import analysis_read_ports
from orchestrator.api.routers import run_analysis as router_module
from orchestrator.application.use_cases.analysis_sarif import AnalysisReadPorts
from orchestrator.domain.entities.analysis import Analysis, AnalysisArtifact
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.db import FakeUnitOfWork

RUN = UUID(int=1)
ANALYSIS = UUID(int=2)
SARIF = b'{"version": "2.1.0", "runs": []}'
HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM = "application/problem+json"
URL = f"/api/v1/runs/{RUN}/analysis/{ANALYSIS}/sarif/gitleaks"


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.analyses = FakeAnalysisRepository()
        self.analyses.add(
            Analysis(
                id=ANALYSIS,
                run_id=RUN,
                repository_path=".",
                status="ok",
                created_at=datetime(2026, 11, 13, tzinfo=UTC),
            )
        )
        self.analyses.add_artifact(
            AnalysisArtifact(
                id=new_id(),
                analysis_id=ANALYSIS,
                tool="gitleaks",
                media_type="application/sarif+json",
                body=SARIF,
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


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_the_stored_sarif_is_served_as_sarif_json(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(URL)

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith("application/sarif+json")
    assert response.content == SARIF


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/runs/{RUN}/analysis/{ANALYSIS}/sarif/osv-scanner",
        f"/api/v1/runs/{RUN}/analysis/{ANALYSIS}/sarif/summary",
        f"/api/v1/runs/{UUID(int=9)}/analysis/{ANALYSIS}/sarif/gitleaks",
        f"/api/v1/runs/{RUN}/analysis/{UUID(int=9)}/sarif/gitleaks",
    ],
    ids=["unknown tool", "summary", "another run", "no analysis"],
)
async def test_everything_else_is_404_problem_json(api: Api, path: str) -> None:
    async with api.client() as client:
        response = await client.get(path)

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_malformed_id_is_422_and_a_missing_bearer_401(api: Api) -> None:
    async with api.client() as client:
        invalid = await client.get(f"/api/v1/runs/{RUN}/analysis/nope/sarif/gitleaks")
    async with api.client(auth=False) as client:
        anonymous = await client.get(URL)

    assert invalid.status_code == HTTP_UNPROCESSABLE
    assert anonymous.status_code == HTTP_UNAUTHORIZED


def test_the_route_declares_sarif_json_and_the_two_problem_answers() -> None:
    [route] = router_module.router.routes
    declared = route.responses  # type: ignore[attr-defined]

    assert "application/sarif+json" in declared[HTTP_OK]["content"]
    assert {HTTP_NOT_FOUND, HTTP_UNPROCESSABLE} <= set(declared)
