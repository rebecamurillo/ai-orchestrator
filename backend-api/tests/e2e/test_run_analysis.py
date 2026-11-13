"""Epic run-metrics 5 against the real stack: the `metrics.analyse` row, the analyses behind a
result version, the stored SARIF, a manual calculation's part C, and the comparison's diff
size (SPEC CAP-1, CAP-2, CAP-4, CAP-5).

The counts, the base rule and the classifier are settled over fakes and recorded tool outputs
by the stories' unit tests. What only a running stack shows: the step kind is registered and
planned from a Template posted through the real endpoint, the analysis fetches a commit the Run
really pushed to its origin and runs the tools the image carries, the DBOS calculation attaches
the pending analysis to v1, the routers are mounted behind the bearer, and the comparison reads
the stored analyses.

Every Template is a fresh `e2e-analysis-<uuid>` name the test owns (member hard rule 6). Every
Run ends terminal inside the module fixtures, so no Repository partition or active-Run slot is
left held for the modules after it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating
from tests.e2e.test_run_creation import RUNS, clone_check, create_repository
from tests.e2e.test_run_metrics_versions import ROLE_LEAF, save, start, wait_for_version
from tests.e2e.test_signals import wait_for

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
SECOND = 2

PROJECTS = "/api/v1/projects"
COMPARE = "/api/v1/metrics/compare"
PROBLEM = "application/problem+json"
SARIF = "application/sarif+json"
TERMINAL = {"done", "failed", "cancelled"}
ANALYSE_KIND = "metrics.analyse"
ROOT = "."
NOT_RUN = "not run"
RAW_ONLY = "raw only"
NO_PUSHED_HEAD = "commit missing: no pushed head"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

#: The change the Run pushes: three production lines, one of them a type escape.
PRODUCTION_LINES = 3
TYPE_ESCAPES = 1

#: Check out a branch, write a small change, commit and push it, analyse, then one more row
#: that proves the Run walks on past the analysis.
ANALYSED = """\
name: {name}
version: 1
description: e2e analysis fixture
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
steps:
  - id: checkout
    uses: git.worktree
    with: {{ base: "{{{{base_branch}}}}", branch: "feat/e2e-analysis" }}
    gate: deterministic
  - id: change
    uses: shell
    with:
      command: |
        mkdir -p src
        echo 'export const a = 1 as any;' > src/app.ts
        echo 'export const b = 2;' >> src/app.ts
        echo 'export const c = 3;' >> src/app.ts
    gate: deterministic
  - id: commit
    uses: git.commit
    with: {{ message: "feat: e2e analysis change" }}
    gate: deterministic
  - id: push
    uses: git.push
    with: {{ branch: "feat/e2e-analysis" }}
    gate: deterministic
  - id: metrics
    uses: metrics.analyse
  - id: after
    uses: shell
    with: {{ command: 'true' }}
    gate: deterministic
"""


@dataclass(frozen=True)
class Analysed:
    """A `done` Run that pushed a change and analysed it: v1 from the workflow step, v2 manual."""

    run: dict[str, Any]
    detail: dict[str, Any]
    v1: dict[str, Any]
    v2: dict[str, Any]


@dataclass(frozen=True)
class Plain:
    """A `done` shell-only Run of the same project: v1 with no analysis, v2 manual."""

    run: dict[str, Any]
    v1: dict[str, Any]
    v2: dict[str, Any]


# ── fixtures ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=30.0) as client:
        yield client


@pytest.fixture(scope="module")
def repository_id(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    response = api.post(PROJECTS, json={"name": f"e2e-analysis-project-{uuid4().hex[:12]}"})
    assert response.status_code == HTTP_CREATED, response.text
    project_id = str(response.json()["id"])
    repository = create_repository(
        api, project_id, fixtures.make(manifest_stating(settings.bmad_version))
    )
    clone_check(api, repository)
    return repository


def analyses_of(api: httpx.Client, run_id: str, v: int | None = None) -> dict[str, Any]:
    params = {} if v is None else {"v": v}
    response = api.get(f"{RUNS}/{run_id}/analysis", params=params)
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


def recalculate(api: httpx.Client, run_id: str) -> None:
    queued = api.post(f"{RUNS}/{run_id}/metrics/calculate")
    assert queued.status_code == HTTP_ACCEPTED, queued.text
    wait_for_version(api, run_id, SECOND)


def values_of(api: httpx.Client, run_id: str, v: int) -> list[dict[str, Any]]:
    response = api.get(f"{RUNS}/{run_id}/metrics", params={"v": v})
    assert response.status_code == HTTP_OK, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def version(api: httpx.Client, run_id: str, n: int) -> dict[str, Any]:
    versions = wait_for_version(api, run_id, n)
    return next(v for v in versions if v["n"] == n)


@pytest.fixture(scope="module")
def analysed(api: httpx.Client, repository_id: str) -> Analysed:
    name = f"e2e-analysis-{uuid4().hex}"
    save(api, name, ANALYSED.format(name=name))
    run = start(api, name, repository_id)
    assert wait_for(api, run["id"], TERMINAL) == "done"
    detail = api.get(f"{RUNS}/{run['id']}/detail")
    assert detail.status_code == HTTP_OK, detail.text
    v1 = version(api, run["id"], 1)
    recalculate(api, run["id"])
    return Analysed(run, detail.json(), v1, version(api, run["id"], SECOND))


@pytest.fixture(scope="module")
def plain(api: httpx.Client, repository_id: str, analysed: Analysed) -> Plain:
    name = f"e2e-analysis-{uuid4().hex}"
    save(api, name, ROLE_LEAF.format(name=name, role="verify"))
    run = start(api, name, repository_id)
    assert wait_for(api, run["id"], TERMINAL) == "done"
    v1 = version(api, run["id"], 1)
    recalculate(api, run["id"])
    return Plain(run, v1, version(api, run["id"], SECOND))


def only_analysis(api: httpx.Client, run_id: str, v: int) -> dict[str, Any]:
    body = analyses_of(api, run_id, v)
    assert body["version"] == v
    assert [item["repository_path"] for item in body["items"]] == [ROOT], body
    item: dict[str, Any] = body["items"][0]
    return item


# ── the bearer and refusals ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "suffix", ["/analysis", f"/analysis/{UNKNOWN_ID}/sarif/gitleaks"], ids=["list", "sarif"]
)
def test_the_analysis_routes_need_the_bearer(stack: str, suffix: str) -> None:
    response = httpx.get(f"{stack}{RUNS}/{UNKNOWN_ID}{suffix}", timeout=10.0)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM)


def test_the_analyses_of_an_unknown_run_are_a_404_problem(api: httpx.Client) -> None:
    response = api.get(f"{RUNS}/{UNKNOWN_ID}/analysis")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


@pytest.mark.parametrize("suffix", ["/analysis?v=0", "/analysis/not-a-uuid/sarif/gitleaks"])
def test_an_invalid_path_or_query_value_is_a_422(api: httpx.Client, suffix: str) -> None:
    response = api.get(f"{RUNS}/{UNKNOWN_ID}{suffix}")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)


# ── the workflow step (story 4) ─────────────────────────────────────────────────────────


def test_the_analysis_row_ends_done_and_the_next_row_runs(analysed: Analysed) -> None:
    steps = sorted(analysed.detail["steps"], key=lambda step: step["seq"])
    kinds = [step["kind"] for step in steps]
    row = steps[kinds.index(ANALYSE_KIND)]
    after = steps[kinds.index(ANALYSE_KIND) + 1]

    assert row["status"] == "done", row
    assert row["gate"] == "unvalidated", row
    assert after["path"] == "after"
    assert after["status"] == "done", after


def test_v1_holds_the_workflow_steps_analysis(api: httpx.Client, analysed: Analysed) -> None:
    item = only_analysis(api, analysed.run["id"], 1)

    assert "workflow_step" in analysed.v1["entry_point"]
    assert item["status"] in {"ok", "partial"}, item
    assert item["head"] and item["base"], item
    assert item["base"] != item["head"]
    assert item["base_branch"] == "main"
    assert item["commits_outside_run"] == 0
    assert {tool["tool"] for tool in item["tools"]} >= {
        "gitleaks",
        "osv-scanner",
        "jscpd",
        "lizard",
    }


def test_v1_counts_the_pushed_change(api: httpx.Client, analysed: Analysed) -> None:
    values = values_of(api, analysed.run["id"], 1)
    run_rows = [v for v in values if v["scope_type"] == "run"]
    added = next(
        v for v in run_rows if v["metric_id"] == "code.lines_added" and v["source"] == "production"
    )
    escapes = [
        v
        for v in run_rows
        if v["metric_id"] == "code.type_escapes_added"
        and v["value_num"] is not None
        and "per_100" not in (v["source"] or "")
    ]
    rates = [
        v
        for v in run_rows
        if v["metric_id"] == "code.type_escapes_added" and "per_100" in (v["source"] or "")
    ]

    assert Decimal(added["value_num"]) == PRODUCTION_LINES
    assert sum(Decimal(v["value_num"]) for v in escapes) == TYPE_ESCAPES
    assert rates, "a rate row is stored beside the raw count"
    assert all(v["missing"] == RAW_ONLY for v in rates), rates
    assert all(
        v["method_id"].startswith("code.") for v in values if v["metric_id"].startswith("code.")
    )


# ── the SARIF download (story 4) ────────────────────────────────────────────────────────


def test_each_stored_sarif_downloads_decompressed(api: httpx.Client, analysed: Analysed) -> None:
    item = only_analysis(api, analysed.run["id"], 1)
    assert "gitleaks" in item["sarif_tools"], item

    for tool in item["sarif_tools"]:
        response = api.get(
            f"{RUNS}/{analysed.run['id']}/analysis/{item['analysis_id']}/sarif/{tool}"
        )
        assert response.status_code == HTTP_OK, (tool, response.text)
        assert response.headers["content-type"].startswith(SARIF)
        assert "runs" in json.loads(response.content), tool


@pytest.mark.parametrize("tool", ["no-such-tool", "summary"])
def test_a_tool_with_no_stored_sarif_is_a_404(
    api: httpx.Client, analysed: Analysed, tool: str
) -> None:
    item = only_analysis(api, analysed.run["id"], 1)

    response = api.get(f"{RUNS}/{analysed.run['id']}/analysis/{item['analysis_id']}/sarif/{tool}")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


def test_another_runs_analysis_is_a_404(
    api: httpx.Client, analysed: Analysed, plain: Plain
) -> None:
    item = only_analysis(api, analysed.run["id"], 1)

    response = api.get(f"{RUNS}/{plain.run['id']}/analysis/{item['analysis_id']}/sarif/gitleaks")

    assert response.status_code == HTTP_NOT_FOUND


# ── the manual calculation (story 4) ────────────────────────────────────────────────────


def test_a_manual_calculation_analyses_afresh(api: httpx.Client, analysed: Analysed) -> None:
    first = only_analysis(api, analysed.run["id"], 1)
    second = only_analysis(api, analysed.run["id"], SECOND)

    assert "manual" in analysed.v2["entry_point"]
    assert second["analysis_id"] != first["analysis_id"]
    assert (second["base"], second["head"]) == (first["base"], first["head"])
    assert any(v["metric_id"].startswith("code.") for v in values_of(api, analysed.run["id"], 2))


def test_a_run_without_the_step_has_no_analysis_in_v1(api: httpx.Client, plain: Plain) -> None:
    body = analyses_of(api, plain.run["id"], 1)

    assert body["items"] == []
    assert "workflow_step" not in plain.v1["entry_point"]


def test_a_manual_calculation_names_the_missing_pushed_head(
    api: httpx.Client, plain: Plain
) -> None:
    item = only_analysis(api, plain.run["id"], SECOND)

    assert item["status"] == "failed"
    assert item["reason"] == NO_PUSHED_HEAD
    assert item["head"] is None


def test_the_latest_version_is_read_without_v(api: httpx.Client, plain: Plain) -> None:
    assert analyses_of(api, plain.run["id"])["version"] == SECOND


# ── the comparison (story 5) ────────────────────────────────────────────────────────────


def test_diff_size_reads_not_run_only_for_a_version_without_analysis(
    api: httpx.Client, analysed: Analysed, plain: Plain
) -> None:
    a, b = analysed.run["id"], plain.run["id"]
    response = api.get(COMPARE, params={"runs": f"{a},{b}", "v": f"{b}:1"})
    assert response.status_code == HTTP_OK, response.text
    diff_size = response.json()["diff_size"]

    assert diff_size[b] == NOT_RUN
    assert diff_size[a].startswith(f"+{PRODUCTION_LINES} "), diff_size
