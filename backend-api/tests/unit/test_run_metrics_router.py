"""The four run-metrics routes over fakes (epic 2 story 5: AC3, AC4, AC6, AC9)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import httpx
import pytest

from orchestrator.api.providers_metrics import calculate_ports, metrics_query_ports
from orchestrator.api.routers import run_metrics as router_module
from orchestrator.api.schemas.metric_results import MetricValueOut
from orchestrator.application.use_cases.metric_calculations import CalculatePorts
from orchestrator.application.use_cases.metrics_read import MetricsQueryPorts
from orchestrator.domain.entities.metric_results import MetricCalculation, ResultVersion
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.metrics_fixed_run import RUN_ID, T0, build_fixed_run
from tests.unit.application.test_metric_versions import stored
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.metric_results import (
    FakeMetricCalculationRepository,
    FakeResultVersionRepository,
)

TWO = 2
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

PROBLEM = "application/problem+json"
BASE = f"/api/v1/runs/{RUN_ID}/metrics"


class Api:
    def __init__(self, env: dict[str, str], status: str = "done") -> None:
        fixed = build_fixed_run()
        self.runs = fixed.ports.runs
        self.runs.runs[RUN_ID] = fixed.run.model_copy(update={"status": status})  # type: ignore[attr-defined]
        self.read = fixed.ports
        self.versions = FakeResultVersionRepository()
        self.calculations = FakeMetricCalculationRepository()
        self.uow = FakeUnitOfWork()
        self.engine = FakeWorkflowEngine(uow=self.uow)
        self.app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[metrics_query_ports] = self._query
        self.app.dependency_overrides[calculate_ports] = self._calculate
        self.token = env["ORCHESTRATOR_TOKEN"]

    def _query(self) -> Iterator[MetricsQueryPorts]:
        yield MetricsQueryPorts(self.read, self.versions, self.calculations)

    def _calculate(self) -> Iterator[CalculatePorts]:
        yield CalculatePorts(
            runs=self.runs,
            calculations=self.calculations,
            versions=self.versions,
            engine=self.engine,
            clock=self.read.clock,
            uow=self.uow,
        )

    def version(self, n: int) -> None:
        version = ResultVersion(
            id=new_id(),
            run_id=RUN_ID,
            n=n,
            calculated_at=T0,
            entry_point=("manual",),
            methods=("a.x@1",),
        )
        self.versions.add(version, [stored(scope_key=f"v{n}", value_num=Decimal("1.50"))])

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


async def test_a_manual_calculation_is_accepted_and_enqueued(api: Api) -> None:
    api.version(1)

    async with api.client() as client:
        response = await client.post(f"{BASE}/calculate")

    body = response.json()
    assert response.status_code == HTTP_ACCEPTED
    assert (body["target_n"], body["state"], body["entry_point"]) == (2, "queued", ["manual"])
    assert [name for name, _ in api.engine.calls] == ["enqueue_calculation"]


async def test_a_calculation_in_progress_answers_409_problem_json(api: Api) -> None:
    api.calculations.add(
        MetricCalculation(
            id=new_id(),
            run_id=RUN_ID,
            target_n=1,
            state="queued",
            entry_point=("at_attempt_end",),
            queued_at=T0,
        )
    )

    async with api.client() as client:
        response = await client.post(f"{BASE}/calculate")

    assert response.status_code == HTTP_CONFLICT
    assert response.headers["content-type"].startswith(PROBLEM)
    assert len(api.calculations.rows) == 1


async def test_a_live_run_answers_409_and_an_unknown_run_404(env: dict[str, str]) -> None:
    live = Api(env, "running")

    async with live.client() as client:
        refused = await client.post(f"{BASE}/calculate")
        unknown = await client.post(f"/api/v1/runs/{new_id()}/metrics/calculate")

    assert refused.status_code == HTTP_CONFLICT
    assert unknown.status_code == HTTP_NOT_FOUND
    assert unknown.headers["content-type"].startswith(PROBLEM)


async def test_v_selects_a_version_and_latest_is_the_default(api: Api) -> None:
    api.version(1)
    api.version(2)

    async with api.client() as client:
        first = await client.get(BASE, params={"v": 1})
        latest = await client.get(BASE)
        missing = await client.get(BASE, params={"v": 9})
        invalid = await client.get(BASE, params={"v": 0})

    assert (first.json()["version"], first.json()["latest"]) == (1, 2)
    assert latest.json()["version"] == TWO
    item = latest.json()["items"][0]
    assert item["value_num"] == "1.50"
    assert item["origin"]["template_name"] == "t"
    assert missing.status_code == HTTP_NOT_FOUND
    assert invalid.status_code == HTTP_UNPROCESSABLE


async def test_a_live_run_answers_values_so_far(env: dict[str, str]) -> None:
    live = Api(env, "running")

    async with live.client() as client:
        response = await client.get(BASE)

    body = response.json()
    assert (body["version"], body["values_so_far"]) == (None, True)
    assert body["items"]
    assert all(item["origin"] is None for item in body["items"])


async def test_an_ended_run_without_a_version_answers_an_empty_list(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(BASE)

    assert response.json() == {
        "run_id": str(RUN_ID),
        "version": None,
        "latest": None,
        "values_so_far": False,
        "items": [],
    }


async def test_the_versions_page_lists_dates_entry_points_and_changes(api: Api) -> None:
    api.version(1)
    api.version(2)

    async with api.client() as client:
        response = await client.get(f"{BASE}/versions")

    body = response.json()
    assert body["next_cursor"] is None
    assert [(v["n"], v["entry_point"], v["methods_changed"]) for v in body["items"]] == [
        (1, ["manual"], []),
        (2, ["manual"], []),
    ]
    assert body["items"][0]["calculated_at"].startswith("2026-01-01")


async def test_a_calculation_reports_its_state_and_output(api: Api) -> None:
    api.calculations.add(
        MetricCalculation(
            id=new_id(),
            run_id=RUN_ID,
            target_n=1,
            state="failed",
            entry_point=("manual",),
            queued_at=T0,
            ended_at=T0,
            output="RuntimeError: boom",
        )
    )

    async with api.client() as client:
        found = await client.get(f"{BASE}/calculations/1")
        absent = await client.get(f"{BASE}/calculations/2")
        zero = await client.get(f"{BASE}/calculations/0")

    assert (found.json()["state"], found.json()["output"]) == ("failed", "RuntimeError: boom")
    assert absent.status_code == HTTP_NOT_FOUND
    assert zero.status_code == HTTP_UNPROCESSABLE


async def test_the_routes_need_the_bearer(api: Api) -> None:
    async with api.client(auth=False) as client:
        response = await client.get(BASE)

    assert response.status_code == HTTP_UNAUTHORIZED


def test_the_router_declares_the_four_operations() -> None:
    operations = {(r.path, tuple(sorted(r.methods))) for r in router_module.router.routes}  # type: ignore[attr-defined]
    assert operations == {
        ("/runs/{run_id}/metrics", ("GET",)),
        ("/runs/{run_id}/metrics/versions", ("GET",)),
        ("/runs/{run_id}/metrics/calculate", ("POST",)),
        ("/runs/{run_id}/metrics/calculations/{n}", ("GET",)),
    }


def test_a_figure_is_written_as_a_plain_decimal_string() -> None:
    out = MetricValueOut.of(stored(value_num=Decimal("1E+2")))

    assert out.value_num == "100"
