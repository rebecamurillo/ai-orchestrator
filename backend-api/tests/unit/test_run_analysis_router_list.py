"""`GET /runs/{id}/analysis` and the comparison's new fields over fakes (epic 5 story 5)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest

from orchestrator.api.providers_metrics import run_analyses_ports
from orchestrator.api.routers import run_analyses as router_module
from orchestrator.api.schemas.metrics_compare import CompareOut
from orchestrator.api.schemas.run_analyses import RunAnalysesOut
from orchestrator.application.use_cases.metrics_compare import compare_runs
from orchestrator.application.use_cases.run_analyses import RunAnalysesPorts, run_analyses
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.entities.metric_results import ResultVersion
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.test_metrics_compare_static import _analysed, _world
from tests.unit.application.test_metrics_spend import a_project, a_run
from tests.unit.fakes.analysis import FakeAnalysisRepository
from tests.unit.fakes.metric_results import FakeResultVersionRepository
from tests.unit.fakes.run_records import FakeRunRepositoryRecords
from tests.unit.fakes.runs import FakeRunRepository

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
PROBLEM = "application/problem+json"
NOW = datetime(2026, 11, 13, tzinfo=UTC)


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.run = a_run(a_project("p"))
        self.runs = FakeRunRepository()
        self.runs.add(self.run)
        self.versions = FakeResultVersionRepository()
        self.analyses = FakeAnalysisRepository()
        found = Analysis(
            id=new_id(), run_id=self.run.id, repository_path=".", status="ok", created_at=NOW
        )
        self.analyses.add(found)
        self.versions.add(
            ResultVersion(
                id=new_id(),
                run_id=self.run.id,
                n=1,
                calculated_at=NOW,
                entry_point=("manual",),
                methods=(),
                analysis_ids=(found.id,),
            ),
            [],
        )
        self.app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[run_analyses_ports] = self._ports
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _ports(self) -> Iterator[RunAnalysesPorts]:
        yield RunAnalysesPorts(self.runs, self.versions, self.analyses, FakeRunRepositoryRecords())

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


async def test_the_list_answers_the_shown_version(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/runs/{api.run.id}/analysis")

    body = response.json()
    assert response.status_code == HTTP_OK
    assert body["version"] == 1
    assert [item["repository_path"] for item in body["items"]] == ["."]
    assert body["items"][0]["languages"] is None
    assert body["items"][0]["sarif_tools"] == []


async def test_an_unknown_version_is_404_problem_json(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/runs/{api.run.id}/analysis?v=9")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_zero_version_is_refused_and_a_missing_bearer_is_401(api: Api) -> None:
    async with api.client() as client:
        refused = await client.get(f"/api/v1/runs/{api.run.id}/analysis?v=0")
    async with api.client(auth=False) as client:
        anonymous = await client.get(f"/api/v1/runs/{api.run.id}/analysis")

    assert refused.status_code == 422  # noqa: PLR2004
    assert anonymous.status_code == HTTP_UNAUTHORIZED


def test_the_schema_maps_the_use_case_answer(api: Api) -> None:
    ports = RunAnalysesPorts(api.runs, api.versions, api.analyses, FakeRunRepositoryRecords())

    out = RunAnalysesOut.of(run_analyses(ports, api.run.id, 1))

    assert out.version == 1
    assert out.items[0].status == "ok"


def test_the_comparison_payload_carries_the_new_fields() -> None:
    world, analyses = _world()
    one = _analysed(world, analyses, "4.0.5", "one")
    two = _analysed(world, analyses, "4.1.0", "two")

    out = CompareOut.of(compare_runs(world.ports, world.query(one, two)))

    metric = next(m for m in out.metrics if m.metric_id == "code.duplication_added")
    assert metric.tool_versions_differ is True
    assert {(t.tool, t.version) for t in metric.toolsets[one.id]} >= {("jscpd", "4.0.5")}
    assert out.diff_size[one.id] == "+40 \u22122 · 3 files"


def test_the_list_route_declares_its_two_problem_answers() -> None:
    [route] = router_module.router.routes

    assert {HTTP_NOT_FOUND, 422} <= set(route.responses)  # type: ignore[attr-defined]
