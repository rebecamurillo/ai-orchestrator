"""Epic run-metrics 4 story 1 against the real stack: spend this month, a project's Runs, the
comparison and its CSV and JSON files, blind or not (SPEC CAP-1).

The projections are settled over fakes by the story's unit tests. What only a running stack
shows: the router is mounted behind the bearer, the comparison reads the result versions the
DBOS calculation job really stored, and the files a browser downloads carry the declared
header, the declared file name and nothing blind hides.

Every Template is a fresh `e2e-metrics-<uuid>` name the test owns (member hard rule 6). Two
Runs end `done` in one project, one Run is cancelled in another; every Run ends terminal
inside the module fixtures, so no Repository partition or active-Run slot is left held.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating
from tests.e2e.test_run_creation import RUNS, clone_check, create_repository
from tests.e2e.test_run_metrics_versions import ROLE_LEAF, save, start, wait_for_version
from tests.e2e.test_signals import TWO_STEP_TEMPLATE, signal, wait_for

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_UNPROCESSABLE = 422
SECOND = 2

PROJECTS = "/api/v1/projects"
SPEND = "/api/v1/metrics/spend"
METRICS_RUNS = "/api/v1/metrics/runs"
COMPARE = "/api/v1/metrics/compare"
COMPARE_CSV = "/api/v1/metrics/compare.csv"
COMPARE_JSON = "/api/v1/metrics/compare.json"
CATALOGUE = "/api/v1/metrics/catalogue"
TERMINAL = {"done", "failed", "cancelled"}
HIDDEN = "hidden · blind"

#: The CSV columns, in order, exactly as story 1 lists them.
EXPORT_COLUMNS = (
    "run_id run_label result_version metric_id method_id scope_type scope_key scope_label "
    "role model repository attempt_n source value_num unit missing carried_from component_of "
    "additive calculated_at entry_point project_id template_name template_version harness "
    "origin_model origin_repository branch commit base_commit"
).split()
SPEND_FIELDS = set(
    "project_id project_name gateway harness runs cancelled gateway_reported harness_reported "
    "subscription".split()
)


@dataclass(frozen=True)
class Pair:
    """Two `done` Runs of one project: A (created first, with v1 and v2) and B (v1)."""

    project_id: str
    project_name: str
    template: str
    a: dict[str, Any]
    b: dict[str, Any]


@dataclass(frozen=True)
class Cancelled:
    """One Run of another project, cancelled at its checkpoint."""

    project_id: str
    run_id: str
    selectable_while_live: bool


# ── fixtures ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=10.0) as client:
        yield client


def new_repository(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> tuple[str, str, str]:
    """A fresh Project (id, name) and its clone-checked repository; the name is file-safe."""
    name = f"e2e-metrics-project-{uuid4().hex[:12]}"
    response = api.post(PROJECTS, json={"name": name})
    assert response.status_code == HTTP_CREATED, response.text
    project_id = str(response.json()["id"])
    repository_id = create_repository(
        api, project_id, fixtures.make(manifest_stating(settings.bmad_version))
    )
    clone_check(api, repository_id)
    return project_id, name, repository_id


@pytest.fixture(scope="module")
def pair(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> Pair:
    template = f"e2e-metrics-{uuid4().hex}"
    save(api, template, ROLE_LEAF.format(name=template, role="verify"))
    project_id, project_name, repository_id = new_repository(api, fixtures, settings)

    a = start(api, template, repository_id, label=f"compare label A {uuid4().hex[:8]}")
    assert wait_for(api, a["id"], TERMINAL) == "done"
    b = start(api, template, repository_id, label=f"compare label B {uuid4().hex[:8]}")
    assert wait_for(api, b["id"], TERMINAL) == "done"

    wait_for_version(api, a["id"], 1)
    wait_for_version(api, b["id"], 1)
    queued = api.post(f"{RUNS}/{a['id']}/metrics/calculate")
    assert queued.status_code == HTTP_ACCEPTED, queued.text
    wait_for_version(api, a["id"], SECOND)
    return Pair(project_id, project_name, template, a, b)


@pytest.fixture(scope="module")
def cancelled(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> Cancelled:
    template = f"e2e-metrics-{uuid4().hex}"
    branch = f"e2e-metrics-{uuid4().hex[:8]}"
    save(api, template, TWO_STEP_TEMPLATE.format(name=template, branch=branch))
    project_id, _, repository_id = new_repository(api, fixtures, settings)
    run_id = start(api, template, repository_id)["id"]
    try:
        wait_for(api, run_id, {"needs_you"})
        listed = api.get(METRICS_RUNS, params={"project": project_id}).json()["items"]
        selectable = next(item["selectable"] for item in listed if item["id"] == run_id)
    finally:
        assert signal(api, run_id, "cancel", confirm=True).status_code == HTTP_OK
    assert wait_for(api, run_id, TERMINAL) == "cancelled"
    return Cancelled(project_id, run_id, selectable)


def compare_params(*run_ids: str, **extra: str) -> dict[str, str]:
    return {"runs": ",".join(run_ids), **extra}


def problem(response: httpx.Response, status: int) -> None:
    assert response.status_code == status, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


def todays_file_names(project: str, extension: str) -> set[str]:
    """Today's name, and yesterday's when the request straddled midnight UTC."""
    today = datetime.now(UTC)
    days = {today, today - timedelta(seconds=60)}
    return {f'attachment; filename="{project}-compare-{day:%Y-%m-%d}.{extension}"' for day in days}


# ── the bearer ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "params"),
    [
        (SPEND, {}),
        (METRICS_RUNS, {"project": str(uuid4())}),
        (COMPARE, {"runs": f"{uuid4()},{uuid4()}"}),
        (COMPARE_CSV, {"runs": f"{uuid4()},{uuid4()}"}),
        (COMPARE_JSON, {"runs": f"{uuid4()},{uuid4()}"}),
    ],
)
def test_every_new_operation_needs_the_bearer(
    client: httpx.Client, path: str, params: dict[str, str]
) -> None:
    response = client.get(path, params=params)

    problem(response, HTTP_UNAUTHORIZED)


# ── refusals ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", [COMPARE, COMPARE_CSV, COMPARE_JSON])
def test_a_comparison_of_fewer_than_two_runs_is_refused(api: httpx.Client, path: str) -> None:
    run_id = str(uuid4())

    for runs in (run_id, f"{run_id},{run_id}"):
        problem(api.get(path, params={"runs": runs}), HTTP_UNPROCESSABLE)


def test_runs_of_two_projects_are_not_comparable(
    api: httpx.Client, pair: Pair, cancelled: Cancelled
) -> None:
    response = api.get(COMPARE, params=compare_params(pair.a["id"], cancelled.run_id))

    problem(response, HTTP_UNPROCESSABLE)


# ── spend this month and a project's Runs ───────────────────────────────────────────────


def test_spend_this_month_counts_each_project_and_its_cancelled_runs_apart(
    api: httpx.Client, pair: Pair, cancelled: Cancelled
) -> None:
    response = api.get(SPEND)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["next_cursor"] is None
    by_project = {item["project_id"]: item for item in body["items"]}
    for item in by_project.values():
        assert set(item) == SPEND_FIELDS, item
        assert Decimal(item["gateway"]) >= Decimal(item["cancelled"]["gateway"]) >= 0, item
        assert Decimal(item["harness"]) >= Decimal(item["cancelled"]["harness"]) >= 0, item

    ours = by_project[pair.project_id]
    assert ours["project_name"] == pair.project_name
    assert ours["runs"] == SECOND
    assert ours["cancelled"]["runs"] == 0

    other = by_project[cancelled.project_id]
    assert other["runs"] == 1
    assert other["cancelled"]["runs"] == 1
    assert Decimal(other["cancelled"]["gateway"]) == Decimal(other["gateway"])
    assert Decimal(other["cancelled"]["harness"]) == Decimal(other["harness"])


def test_a_projects_runs_are_listed_newest_first_and_ended_ones_are_selectable(
    api: httpx.Client, pair: Pair
) -> None:
    response = api.get(METRICS_RUNS, params={"project": pair.project_id})

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["next_cursor"] is None
    assert [item["id"] for item in body["items"]] == [pair.b["id"], pair.a["id"]]
    newest, oldest = body["items"]
    assert newest["label"] == pair.b["label"]
    assert newest["label_set_by_operator"] is True
    assert oldest["latest_version"] == SECOND
    for item in body["items"]:
        assert item["status"] == "done"
        assert item["selectable"] is True
        assert item["template_name"] == pair.template
        assert item["latest_version"] is not None


def test_a_live_run_is_not_selectable_and_a_cancelled_one_is(
    api: httpx.Client, cancelled: Cancelled
) -> None:
    response = api.get(METRICS_RUNS, params={"project": cancelled.project_id})

    assert response.status_code == HTTP_OK, response.text
    (item,) = response.json()["items"]
    assert cancelled.selectable_while_live is False
    assert item["status"] == "cancelled"
    assert item["selectable"] is True


# ── the comparison ──────────────────────────────────────────────────────────────────────


def test_the_comparison_reads_runs_in_selection_order_at_their_selected_versions(
    api: httpx.Client, pair: Pair
) -> None:
    a_id, b_id = pair.a["id"], pair.b["id"]
    catalogue = [entry["id"] for entry in api.get(CATALOGUE).json()["items"]]

    response = api.get(COMPARE, params=compare_params(b_id, a_id, v=f"{a_id}:1"))

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["project_id"] == pair.project_id
    b_header, a_header = body["runs"]
    assert [b_header["run_id"], a_header["run_id"]] == [b_id, a_id]
    assert a_header["selected_version"] == 1
    assert a_header["versions_available"] == [1, SECOND]
    assert b_header["selected_version"] == 1
    for header, run in ((a_header, pair.a), (b_header, pair.b)):
        assert header["short_id"]
        assert run["id"].replace("-", "").startswith(header["short_id"])
        assert header["label"] == run["label"]
        assert header["template_name"] == pair.template
        assert header["template_version"] == "1"
        assert header["status"] == "done"

    same_work = body["same_work"]
    assert set(same_work["runs"]) == {a_id, b_id}
    assert same_work["differs"] == (same_work["runs"][a_id] != same_work["runs"][b_id])
    for run_id in (a_id, b_id):
        assert "." in same_work["runs"][run_id]["base_commits"]

    metric_ids = [metric["metric_id"] for metric in body["metrics"]]
    assert metric_ids, body
    assert metric_ids == [metric_id for metric_id in catalogue if metric_id in metric_ids]
    for metric in body["metrics"]:
        assert set(metric["cells"]) == {a_id, b_id}
        methods = {tuple(found) for found in metric["methods"].values() if found}
        assert metric["methods_differ"] == (len(methods) > 1), metric


def test_the_latest_version_is_read_when_none_is_named(api: httpx.Client, pair: Pair) -> None:
    response = api.get(COMPARE, params=compare_params(pair.a["id"], pair.b["id"]))

    assert response.status_code == HTTP_OK, response.text
    a_header, _ = response.json()["runs"]
    assert a_header["selected_version"] == SECOND


# ── the export files ────────────────────────────────────────────────────────────────────


def test_the_csv_has_the_declared_header_numbers_only_and_the_declared_name(
    api: httpx.Client, pair: Pair
) -> None:
    a_id, b_id = pair.a["id"], pair.b["id"]

    response = api.get(COMPARE_CSV, params=compare_params(a_id, b_id, v=f"{a_id}:1"))

    assert response.status_code == HTTP_OK, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.headers["content-disposition"] in todays_file_names(pair.project_name, "csv")
    header, *rows = list(csv.reader(io.StringIO(response.text)))
    assert header == EXPORT_COLUMNS
    assert rows, response.text
    records = [dict(zip(header, row, strict=True)) for row in rows]
    assert {record["run_id"] for record in records} == {a_id, b_id}
    for record in records:
        assert not re.search("[A-Za-z]", record["value_num"]), record
        if record["value_num"]:
            Decimal(record["value_num"])
        if record["run_id"] == a_id:
            assert record["result_version"] == "1", record
            assert record["run_label"] == pair.a["label"], record


def test_the_json_holds_runs_rows_and_each_catalogue_entry_once(
    api: httpx.Client, pair: Pair
) -> None:
    a_id, b_id = pair.a["id"], pair.b["id"]

    response = api.get(COMPARE_JSON, params=compare_params(a_id, b_id))

    assert response.status_code == HTTP_OK, response.text
    assert response.headers["content-disposition"] in todays_file_names(pair.project_name, "json")
    body = response.json()
    assert set(body) == {"runs", "rows", "catalogue"}
    assert [header["run_id"] for header in body["runs"]] == [a_id, b_id]
    assert body["rows"], body
    for row in body["rows"]:
        assert list(row) == EXPORT_COLUMNS, row
    catalogue_ids = [entry["id"] for entry in body["catalogue"]]
    assert len(catalogue_ids) == len(set(catalogue_ids))
    assert set(catalogue_ids) == {row["metric_id"] for row in body["rows"]}


# ── blind ───────────────────────────────────────────────────────────────────────────────


def test_blind_hides_labels_and_the_template_from_the_payload_and_both_files(
    api: httpx.Client, pair: Pair
) -> None:
    a_id, b_id = pair.a["id"], pair.b["id"]
    params = compare_params(a_id, b_id, blind="true")

    payload = api.get(COMPARE, params=params)
    csv_file = api.get(COMPARE_CSV, params=params)
    json_file = api.get(COMPARE_JSON, params=params)

    for response in (payload, csv_file, json_file):
        assert response.status_code == HTTP_OK, response.text
        for hidden in (pair.a["label"], pair.b["label"], pair.template):
            assert hidden not in response.text, hidden
        for shown in ("R1", "R2", a_id, b_id):
            assert shown in response.text, shown

    for header in (*payload.json()["runs"], *json_file.json()["runs"]):
        assert header["template_name"] == HIDDEN
        assert header["template_version"] == HIDDEN
        assert all(models == [HIDDEN] for models in header["models_by_role"].values()), header
    assert [header["label"] for header in payload.json()["runs"]] == ["R1", "R2"]
    for row in json_file.json()["rows"]:
        assert row["template_name"] == HIDDEN, row
        assert row["template_version"] == HIDDEN, row
        assert row["run_label"] == ("R1" if row["run_id"] == a_id else "R2"), row
