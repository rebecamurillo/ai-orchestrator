"""Epic run-metrics 6 against the real stack: the findings listing route, Tier 2 and the
findings signals for a repository that declares nothing, and Tier 3 step-produced results from
a Template posted through the real endpoint (SPEC CAP-1, CAP-2, CAP-3, CAP-4).

Matching, parsing, the timeout and the environment of the repository's commands are settled over
fakes and recorded tool outputs by the stories' unit tests. What only a running stack shows: the
findings router is mounted behind the bearer, the template store accepts and refuses a
`metrics:` list, the analysis reads a report the Run really pushed and stores its counts under
the declared id, and the calculation output names a report no entry claims.

Every Template is a fresh `e2e-tier3-<hex>` name the test owns (member hard rule 6). Every Run
ends terminal inside the module fixtures.
"""

from __future__ import annotations

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
from tests.e2e.test_run_metrics_versions import save, start, wait_for_version
from tests.e2e.test_signals import wait_for

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422

PROJECTS = "/api/v1/projects"
TEMPLATES = "/api/v1/templates"
PROBLEM = "application/problem+json"
TERMINAL = {"done", "failed", "cancelled"}
ROOT = "."
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"

TIER2_IDS = (
    "code.linter_warnings_new",
    "code.typecheck_errors_new",
    "code.coverage_changed_lines",
    "code.tests_executed",
    "code.fail_to_pass",
)
FINDING_IDS = ("code.findings_security", "code.findings_bug")
TIER2_NOT_DECLARED = "n/a — tier 2 not declared"
NO_RULES = "n/a — no rules declared"
INVALID_STEP_METRIC_ID = "metric id must be step.{template}.{name}"

HELDOUT_PASSED = 18
HELDOUT_FAILED = 2
HELDOUT_PATH = "out/heldout.xml"
OTHER_PATH = "out/other.xml"


def metrics_entry(metric_id: str) -> str:
    """One template-level catalogue entry; braces doubled for `str.format`."""
    return f"""\
metrics:
  - id: {metric_id}
    label: held-out tests
    group: step
    level: A
    scopes: [run]
    unit: tests
    source: the held-out suite
    additive: false
    fingerprint_group: false
    missing_words: []
    methods:
      - {{{{ n: 1, description: reads the report }}}}
    format: junit
    path: {HELDOUT_PATH}
"""


#: Writes two JUnit reports — the declared one (18 passed, 2 failed) and one nobody declared —
#: commits and pushes them, then analyses.
STEPS = """\
steps:
  - id: checkout
    uses: git.worktree
    with: {{ base: "{{{{base_branch}}}}", branch: "feat/e2e-tier3" }}
    gate: deterministic
  - id: reports
    uses: shell
    with:
      command: |
        mkdir -p out
        {{ echo '<testsuite name="heldout">'
          i=0
          while [ $i -lt 18 ]; do
            echo "<testcase classname=\\"h\\" name=\\"p$i\\"/>"; i=$((i+1))
          done
          echo '<testcase classname="h" name="f1"><failure message="no"/></testcase>'
          echo '<testcase classname="h" name="f2"><failure message="no"/></testcase>'
          echo '</testsuite>'; }} > out/heldout.xml
        echo '<testsuite name="other">' > out/other.xml
        echo '<testcase classname="o" name="x"/></testsuite>' >> out/other.xml
    gate: deterministic
  - id: commit
    uses: git.commit
    with: {{ message: "test: e2e step reports" }}
    gate: deterministic
  - id: push
    uses: git.push
    with: {{ branch: "feat/e2e-tier3" }}
    gate: deterministic
  - id: metrics
    uses: metrics.analyse
"""

HEAD = """\
name: {name}
version: 1
description: e2e tier 3 fixture
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
"""


def template(name: str, metric_id: str) -> str:
    return (HEAD + metrics_entry(metric_id) + STEPS).format(name=name)


@dataclass(frozen=True)
class Stepped:
    """A `done` Run whose template catalogued one step report, with its v1."""

    name: str
    metric_id: str
    run: dict[str, Any]


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
    response = api.post(PROJECTS, json={"name": f"e2e-tier3-project-{uuid4().hex[:12]}"})
    assert response.status_code == HTTP_CREATED, response.text
    repository = create_repository(
        api, str(response.json()["id"]), fixtures.make(manifest_stating(settings.bmad_version))
    )
    clone_check(api, repository)
    return repository


@pytest.fixture(scope="module")
def stepped(api: httpx.Client, repository_id: str) -> Stepped:
    name = f"e2e-tier3-{uuid4().hex}"
    metric_id = f"step.{name}.heldout_tests"
    save(api, name, template(name, metric_id))
    run = start(api, name, repository_id)
    assert wait_for(api, run["id"], TERMINAL) == "done"
    wait_for_version(api, run["id"], 1)
    return Stepped(name, metric_id, run)


def analyses_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/analysis", params={"v": 1})
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


def root_analysis(api: httpx.Client, run_id: str) -> dict[str, Any]:
    items = analyses_of(api, run_id)["items"]
    assert [item["repository_path"] for item in items] == [ROOT], items
    item: dict[str, Any] = items[0]
    return item


def values_of(api: httpx.Client, run_id: str) -> list[dict[str, Any]]:
    response = api.get(f"{RUNS}/{run_id}/metrics", params={"v": 1})
    assert response.status_code == HTTP_OK, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


# ── the findings route: bearer and refusals (story 4) ───────────────────────────────────


def test_the_findings_route_needs_the_bearer(stack: str) -> None:
    response = httpx.get(f"{stack}{RUNS}/{UNKNOWN_ID}/analysis/{UNKNOWN_ID}/findings", timeout=10.0)

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM)


def test_the_findings_of_an_unknown_analysis_are_a_404_problem(api: httpx.Client) -> None:
    response = api.get(f"{RUNS}/{UNKNOWN_ID}/analysis/{UNKNOWN_ID}/findings")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)


def test_a_non_uuid_analysis_id_is_a_422(api: httpx.Client) -> None:
    response = api.get(f"{RUNS}/{UNKNOWN_ID}/analysis/not-a-uuid/findings")

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.headers["content-type"].startswith(PROBLEM)


def test_an_analysis_without_rules_has_no_findings_listing(
    api: httpx.Client, stepped: Stepped
) -> None:
    item = root_analysis(api, stepped.run["id"])

    response = api.get(f"{RUNS}/{stepped.run['id']}/analysis/{item['analysis_id']}/findings")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM)
    assert item["rule_pack_hash"] is None


# ── a repository that declares nothing (stories 1 and 2) ────────────────────────────────


def test_every_tier2_signal_reads_tier_2_not_declared(api: httpx.Client, stepped: Stepped) -> None:
    values = values_of(api, stepped.run["id"])

    for metric_id in TIER2_IDS:
        rows = [v for v in values if v["metric_id"] == metric_id]
        assert rows, metric_id
        assert all(v["missing"] == TIER2_NOT_DECLARED for v in rows), rows
        assert all(v["value_num"] is None for v in rows), rows


def test_both_finding_signals_read_no_rules_declared(api: httpx.Client, stepped: Stepped) -> None:
    values = values_of(api, stepped.run["id"])

    for metric_id in FINDING_IDS:
        rows = [v for v in values if v["metric_id"] == metric_id]
        assert rows, metric_id
        assert all(v["missing"] == NO_RULES for v in rows), rows


# ── Tier 3: the template store (story 3) ────────────────────────────────────────────────


def test_a_metric_id_without_the_step_prefix_is_refused_with_its_reason(
    api: httpx.Client,
) -> None:
    name = f"e2e-tier3-{uuid4().hex}"

    response = api.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": template(name, "heldout_tests")}
    )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert response.headers["content-type"].startswith(PROBLEM)
    errors = response.json()["errors"]
    assert INVALID_STEP_METRIC_ID in [error["reason"] for error in errors], errors
    assert all(isinstance(error["line"], int) for error in errors), errors


def test_another_templates_prefix_is_refused(api: httpx.Client) -> None:
    name = f"e2e-tier3-{uuid4().hex}"

    response = api.post(
        f"{TEMPLATES}/{name}/versions",
        json={"yaml": template(name, "step.someone-else.heldout_tests")},
    )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert INVALID_STEP_METRIC_ID in [e["reason"] for e in response.json()["errors"]]


# ── Tier 3: the step report imported (story 3) ──────────────────────────────────────────


def test_the_declared_report_is_counted_under_its_id(api: httpx.Client, stepped: Stepped) -> None:
    rows = {
        v["source"]: v
        for v in values_of(api, stepped.run["id"])
        if v["metric_id"] == stepped.metric_id and v["value_num"] is not None
    }

    assert Decimal(rows["passed"]["value_num"]) == HELDOUT_PASSED, rows
    assert Decimal(rows["failed"]["value_num"]) == HELDOUT_FAILED, rows
    assert Decimal(rows["errored"]["value_num"]) == 0
    assert Decimal(rows["skipped"]["value_num"]) == 0
    assert {v["method_id"] for v in rows.values()} == {f"{stepped.metric_id}@1"}


def test_the_analysis_lists_the_templates_step_entry(api: httpx.Client, stepped: Stepped) -> None:
    entries = analyses_of(api, stepped.run["id"])["step_entries"]

    assert [entry["id"] for entry in entries] == [stepped.metric_id], entries
    assert entries[0]["label"] == "held-out tests"


def test_an_undeclared_report_is_named_not_catalogued(api: httpx.Client, stepped: Stepped) -> None:
    response = api.get(f"{RUNS}/{stepped.run['id']}/metrics/calculations/1")
    assert response.status_code == HTTP_OK, response.text
    output = response.json()["output"]

    assert f"not catalogued: {OTHER_PATH}" in output
    assert f"not catalogued: {HELDOUT_PATH}" not in output
    assert not any(
        OTHER_PATH in (v["source"] or "") or "other" in v["metric_id"]
        for v in values_of(api, stepped.run["id"])
        if v["metric_id"].startswith("step.")
    )
