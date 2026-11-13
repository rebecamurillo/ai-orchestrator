"""The five spend, Runs and comparison routes over fakes (epic 4 story 1: AC1, AC7, AC8, AC11)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from decimal import Decimal

import httpx
import pytest

from orchestrator.api.providers_metrics import metrics_compare_ports, metrics_home_ports
from orchestrator.api.routers import metrics as metrics_router
from orchestrator.api.schemas.metrics_compare import CompareExportOut, ExportRowOut
from orchestrator.application.use_cases.metrics_compare import MetricsComparePorts
from orchestrator.application.use_cases.metrics_spend import MetricsHomePorts
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.settings import Settings
from orchestrator.main import create_app
from tests.unit.application.test_metric_versions import PLAIN_ORIGIN, stored
from tests.unit.application.test_metrics_compare import World, run_value
from tests.unit.application.test_metrics_export_rows import HEADER
from tests.unit.application.test_metrics_spend import THIS_MONTH, a_project, a_run
from tests.unit.fakes.metric_results import FakeResultVersionRepository  # noqa: F401

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
PROBLEM = "application/problem+json"
PATHS = (
    "/api/v1/metrics/spend",
    "/api/v1/metrics/runs",
    "/api/v1/metrics/compare",
    "/api/v1/metrics/compare.csv",
    "/api/v1/metrics/compare.json",
)
SECRETS = ("secret label alpha", "secret label beta", "initiative-hub", "claude-opus-5")


class Api:
    def __init__(self, env: dict[str, str]) -> None:
        self.world = World()
        self.a = self.world.run(label="secret label alpha")
        self.b = self.world.run(label="secret label beta")
        origin = PLAIN_ORIGIN.model_copy(
            update={"template_name": "initiative-hub", "origin_model": "claude-opus-5"}
        )
        model = stored(
            "tokens.input",
            origin=origin,
            scope_type="model",
            scope_key="claude-opus-5",
            scope_label="claude-opus-5",
            model="claude-opus-5",
        )
        attempt = stored(
            "tokens.input",
            origin=origin,
            scope_type="attempt",
            scope_key="p#1",
            role="plan",
            model="claude-opus-5",
        )
        for run, figure in ((self.a, "1.5"), (self.b, "2")):
            self.world.version(
                run, 1, [run_value("cost.gateway", figure, origin=origin), model, attempt]
            )
        self.token = env["ORCHESTRATOR_TOKEN"]
        self.app = create_app(Settings(**{k.lower(): v for k, v in env.items()}))
        self.app.dependency_overrides[metrics_compare_ports] = self._compare
        self.app.dependency_overrides[metrics_home_ports] = self._home

    def _compare(self) -> Iterator[MetricsComparePorts]:
        yield self.world.ports

    def _home(self) -> Iterator[MetricsHomePorts]:
        yield MetricsHomePorts(
            projects=self.world.projects,
            runs=self.world.runs,
            versions=self.world.versions,
            fact_sets=self.world.fact_sets,
            run_records=self.world.records,
            clock=self.world.ports.clock,
        )

    def client(self, *, auth: bool = True) -> httpx.AsyncClient:
        headers = {"Authorization": f"Bearer {self.token}"} if auth else {}
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app, raise_app_exceptions=False),
            base_url="http://backend-api",
            headers=headers,
        )

    @property
    def runs(self) -> str:
        return f"runs={self.a.id},{self.b.id}"


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_the_five_paths_are_behind_the_bearer(api: Api) -> None:
    async with api.client(auth=False) as client:
        statuses = [(await client.get(path)).status_code for path in PATHS]

    assert statuses == [HTTP_UNAUTHORIZED] * len(PATHS)
    assert all(path in api.app.openapi()["paths"] for path in PATHS)


async def test_compare_answers_the_payload(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare?{api.runs}")

    body = response.json()
    assert response.status_code == HTTP_OK
    assert [h["label"] for h in body["runs"]] == ["secret label alpha", "secret label beta"]
    assert body["metrics"][0]["metric_id"] == "cost.gateway"
    assert body["metrics"][0]["cells"][str(api.a.id)][0]["value_num"] == "1.5"
    assert body["same_work"]["differs"] is False


@pytest.mark.parametrize(
    "query",
    ["", "runs=nope", "runs={a}", "runs={a},{a}", "runs={a},{b}&v=zzz", "runs={a},{b}&v={a}:x"],
)
async def test_a_bad_selection_is_422_problem_json_on_every_form(api: Api, query: str) -> None:
    query = query.format(a=api.a.id, b=api.b.id)
    async with api.client() as client:
        responses = [
            await client.get(f"/api/v1/metrics/compare{form}?{query}")
            for form in ("", ".csv", ".json")
        ]

    assert [r.status_code for r in responses] == [HTTP_UNPROCESSABLE] * 3
    assert all(r.headers["content-type"].startswith(PROBLEM) for r in responses)


async def test_runs_of_two_projects_are_422(api: Api) -> None:
    other = a_project("orchestrator")
    api.world.projects.add(other)
    stray = a_run(other)
    api.world.runs.add(stray)

    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare?runs={api.a.id},{stray.id}")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_an_unknown_run_or_version_is_404_problem_json(api: Api) -> None:
    async with api.client() as client:
        unknown = await client.get(f"/api/v1/metrics/compare?runs={api.a.id},{new_id()}")
        version = await client.get(f"/api/v1/metrics/compare?{api.runs}&v={api.a.id}:9")
        csv_missing = await client.get(f"/api/v1/metrics/compare.csv?runs={api.a.id},{new_id()}")

    assert [r.status_code for r in (unknown, version, csv_missing)] == [HTTP_NOT_FOUND] * 3
    assert unknown.headers["content-type"].startswith(PROBLEM)


async def test_the_csv_has_the_header_one_row_per_value_and_a_dated_file_name(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare.csv?{api.runs}")

    assert response.status_code == HTTP_OK
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] == (
        'attachment; filename="familio-compare-2026-11-13.csv"'
    )
    assert response.text.splitlines()[0] == HEADER
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == len(("cost", "model", "attempt")) * 2
    assert {r["run_label"] for r in rows} == {"secret label alpha", "secret label beta"}
    assert all(not any(c.isalpha() for c in r["value_num"]) for r in rows)


async def test_a_missing_value_has_an_empty_figure_and_its_word_in_the_file(api: Api) -> None:
    api.world.version(
        api.world.run(),
        1,
        [
            stored(
                "cost.gateway",
                scope_type="run",
                scope_key="run",
                value_num=None,
                missing="not recorded",
            )
        ],
    )
    third = api.world.runs.list()[0]

    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare.csv?runs={api.a.id},{third.id}")

    rows = [r for r in csv.DictReader(io.StringIO(response.text)) if r["missing"]]
    assert [(r["value_num"], r["missing"]) for r in rows] == [("", "not recorded")]


async def test_the_json_holds_runs_rows_and_the_catalogue_once(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare.json?{api.runs}")

    body = response.json()
    assert response.headers["content-disposition"] == (
        'attachment; filename="familio-compare-2026-11-13.json"'
    )
    assert set(body) == {"runs", "rows", "catalogue"}
    assert len(body["rows"]) == len(("cost", "model", "attempt")) * 2
    assert sorted(e["id"] for e in body["catalogue"]) == ["cost.gateway", "tokens.input"]


async def test_a_project_name_never_breaks_the_file_name_header(api: Api) -> None:
    api.world.projects.projects[api.a.project_id] = api.world.project.model_copy(
        update={"name": 'a "b"\r\nX-Evil: 1'}
    )

    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare.csv?{api.runs}")

    assert response.headers["content-disposition"] == (
        'attachment; filename="a-b-X-Evil-1-compare-2026-11-13.csv"'
    )
    assert "x-evil" not in response.headers


async def test_a_nameless_project_falls_back_to_project(api: Api) -> None:
    api.world.projects.projects[api.a.project_id] = api.world.project.model_copy(
        update={"name": "***"}
    )

    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare.json?{api.runs}")

    assert 'filename="project-compare-2026-11-13.json"' in response.headers["content-disposition"]


@pytest.mark.parametrize("form", ["", ".csv", ".json"])
async def test_blind_leaves_no_label_template_or_model_in_the_raw_body(api: Api, form: str) -> None:
    async with api.client() as client:
        response = await client.get(f"/api/v1/metrics/compare{form}?{api.runs}&blind=true")
        open_ = await client.get(f"/api/v1/metrics/compare{form}?{api.runs}")

    assert response.status_code == HTTP_OK
    for secret in SECRETS:
        assert secret not in response.text
        assert secret in open_.text
    assert "R1" in response.text and "R2" in response.text
    assert "hidden · blind" in response.text
    assert str(api.a.id) in response.text and "claude" in response.text
    assert ("done" in response.text) is (form != ".csv")  # the CSV has no status column


async def test_spend_lists_every_project_with_this_months_figures(api: Api) -> None:
    api.world.projects.add(a_project("quiet"))
    api.world.runs.update(
        api.a.model_copy(update={"gateway_spend_usd": Decimal("2.00"), "started_at": THIS_MONTH})
    )

    async with api.client() as client:
        response = await client.get("/api/v1/metrics/spend")

    body = response.json()
    assert response.status_code == HTTP_OK and body["next_cursor"] is None
    by_name = {p["project_name"]: p for p in body["items"]}
    assert (by_name["familio"]["gateway"], by_name["familio"]["runs"]) == ("2.00", 2)
    assert by_name["familio"]["subscription"] is None
    assert (by_name["quiet"]["runs"], by_name["quiet"]["cancelled"]["runs"]) == (0, 0)


async def test_runs_of_a_project_and_404_for_an_unknown_one(api: Api) -> None:
    async with api.client() as client:
        listed = await client.get(f"/api/v1/metrics/runs?project={api.world.project.id}")
        unknown = await client.get(f"/api/v1/metrics/runs?project={new_id()}")
        invalid = await client.get("/api/v1/metrics/runs?project=nope")

    items = listed.json()["items"]
    assert listed.status_code == HTTP_OK and listed.json()["next_cursor"] is None
    assert {i["id"] for i in items} == {str(api.a.id), str(api.b.id)}
    assert items[0]["selectable"] is True and items[0]["latest_version"] == 1
    assert unknown.status_code == HTTP_NOT_FOUND
    assert unknown.headers["content-type"].startswith(PROBLEM)
    assert invalid.status_code == HTTP_UNPROCESSABLE


def test_the_export_row_contract_names_the_documented_columns() -> None:
    assert ",".join(ExportRowOut.model_fields) == HEADER
    assert set(CompareExportOut.model_fields) == {"runs", "rows", "catalogue"}
    assert {route.path for route in metrics_router.router.routes} == {  # type: ignore[attr-defined]
        path.removeprefix("/api/v1") for path in PATHS
    }
