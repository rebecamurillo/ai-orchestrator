"""Epic run-metrics 2 against the real stack: roles, the Run label, per-repository records,
result versions and the gateway-read comparison (SPEC CAP-1, CAP-2, CAP-3, CAP-5, CAP-6).

The rules are settled over fakes by the stories' unit tests. What only a running stack shows:
the routers are mounted behind the bearer, the migrations created the tables and columns with
the declared nullability, the single validator refuses an unknown `role` through the real
template endpoint, a Run that ends really queues a calculation that the DBOS adapter runs to
a stored v1, a manual calculation really yields v2 beside an unchanged v1, and a cancelled
Run gets its v1 too.

Every Template is a fresh `e2e-metrics-<uuid>` name the test owns (member hard rule 6), and
every Run this module creates ends terminal inside its own test, so no Repository partition
or active-Run slot is left held for the modules after it.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating
from tests.e2e.test_run_creation import (
    RUNS,
    TEMPLATES,
    clone_check,
    create_repository,
    project_id_of,
    run_payload,
)
from tests.e2e.test_signals import TWO_STEP_TEMPLATE, signal, wait_for

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_ACCEPTED = 202
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
CHECK_VIOLATION = "23514"

PROJECTS = "/api/v1/projects"
MAX_LABEL = 120
VERSION_TIMEOUT_SECONDS = 90.0
POLL_INTERVAL_SECONDS = 0.5
SECOND = 2
TERMINAL = {"done", "failed", "cancelled"}

#: One shell row with a declared role: the Run ends `done` without a harness.
ROLE_LEAF = (
    "name: {name}\nversion: 1\ndescription: e2e metrics leaf\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: touch\n"
    "    uses: shell\n"
    "    role: {role}\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

INSERT_VALUE = text(
    "insert into public.metric_value (id, version_id, metric_id, method_id, scope_type, "
    "scope_key, unit, value_num, missing, project_id, run_id, template_name, template_version) "
    "values (:id, :version_id, 'cost.gateway', 'cost.gateway@1', 'run', 'run', 'usd', 1, "
    "'not recorded', :project_id, :run_id, 'e2e', 1)"
)
NEW_TABLES = (
    "run_repository",
    "run_commit",
    "metric_calculation",
    "result_version",
    "metric_value",
)


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


@pytest.fixture
def connection(settings: Settings) -> Iterator[Connection]:
    """Reads, and writes the database must refuse, inside a transaction that is rolled back."""
    engine = create_engine_from(settings)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def new_project(api: httpx.Client) -> tuple[str, str]:
    name = f"e2e metrics {uuid4().hex[:12]}"
    response = api.post(PROJECTS, json={"name": name})
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["id"]), name


def new_repository(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> tuple[str, str]:
    """A fresh Project (id, name) and a clone-checked repository of its own (AD-12)."""
    project_id, project_name = new_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository_id = create_repository(api, project_id, url)
    clone_check(api, repository_id)
    return repository_id, project_name


def save(api: httpx.Client, name: str, yaml: str) -> None:
    response = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": yaml})
    assert response.status_code == HTTP_CREATED, response.text


def start(api: httpx.Client, name: str, repository_id: str, **extra: object) -> dict[str, Any]:
    extra.setdefault("project_id", project_id_of(api, repository_id))
    response = api.post(RUNS, json=run_payload(name, repository_id, **extra))
    assert response.status_code == HTTP_CREATED, response.text
    run: dict[str, Any] = response.json()["run"]
    return run


def done_run(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> dict[str, Any]:
    name = f"e2e-metrics-{uuid4().hex}"
    save(api, name, ROLE_LEAF.format(name=name, role="verify"))
    repository_id, _ = new_repository(api, fixtures, settings)
    run = start(api, name, repository_id)
    assert wait_for(api, run["id"], TERMINAL) == "done"
    return run


def versions_of(api: httpx.Client, run_id: str) -> list[dict[str, Any]]:
    response = api.get(f"{RUNS}/{run_id}/metrics/versions")
    assert response.status_code == HTTP_OK, response.text
    items: list[dict[str, Any]] = response.json()["items"]
    return items


def wait_for_version(api: httpx.Client, run_id: str, n: int) -> list[dict[str, Any]]:
    """Poll until version `n` exists; fail with the calculation's state and output if not."""
    deadline = time.monotonic() + VERSION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        versions = versions_of(api, run_id)
        if any(version["n"] == n for version in versions):
            return versions
        calculation = api.get(f"{RUNS}/{run_id}/metrics/calculations/{n}")
        if calculation.status_code == HTTP_OK and calculation.json()["state"] == "failed":
            pytest.fail(f"calculation v{n} of run {run_id} failed: {calculation.json()['output']}")
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"run {run_id} has no version {n} after {VERSION_TIMEOUT_SECONDS:.0f}s")


def _columns(connection: Connection, table: str) -> dict[str, tuple[str, str | None]]:
    rows = connection.execute(
        text(
            "select column_name, is_nullable, column_default from information_schema.columns "
            "where table_schema = 'public' and table_name = :table"
        ),
        {"table": table},
    )
    return {row[0]: (row[1], row[2]) for row in rows}


# ── the bearer and unknown Runs ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", "/metrics"),
        ("GET", "/metrics/versions"),
        ("POST", "/metrics/calculate"),
        ("GET", "/metrics/calculations/1"),
        ("GET", "/metrics/gateway-reads"),
        ("PATCH", ""),
    ],
)
def test_every_new_operation_needs_the_bearer(
    client: httpx.Client, method: str, suffix: str
) -> None:
    response = client.request(method, f"{RUNS}/{uuid4()}{suffix}", json={"label": "x"})

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("GET", "/metrics"),
        ("GET", "/metrics/versions"),
        ("POST", "/metrics/calculate"),
        ("GET", "/metrics/calculations/1"),
        ("GET", "/metrics/gateway-reads"),
        ("PATCH", ""),
    ],
)
def test_an_unknown_run_is_a_404(api: httpx.Client, method: str, suffix: str) -> None:
    response = api.request(method, f"{RUNS}/{uuid4()}{suffix}", json={"label": "x"})

    assert response.status_code == HTTP_NOT_FOUND, response.text
    assert response.headers["content-type"].startswith("application/problem+json")


# ── migrations (stories 1, 2, 3, 5) ─────────────────────────────────────────────────────


def test_the_new_tables_live_in_the_application_schema(connection: Connection) -> None:
    rows = connection.execute(
        text(
            "select table_name from information_schema.tables "
            "where table_schema = 'public' and table_name = any(:names)"
        ),
        {"names": list(NEW_TABLES)},
    )

    assert sorted(row[0] for row in rows) == sorted(NEW_TABLES)


def test_role_and_label_columns_are_not_null_with_defaults(connection: Connection) -> None:
    step_run = _columns(connection, "step_run")
    run = _columns(connection, "run")

    for columns, name in ((step_run, "role"), (run, "label"), (run, "label_set_by_operator")):
        nullable, default = columns[name]
        assert nullable == "NO", name
        assert default is not None, name


def test_a_metric_value_with_both_a_figure_and_a_missing_word_is_refused(
    connection: Connection,
) -> None:
    """Postgres evaluates CHECK before FK triggers, so the unknown parent ids are no obstacle."""
    with pytest.raises(IntegrityError) as refused:
        connection.execute(
            INSERT_VALUE,
            {"id": uuid4(), "version_id": uuid4(), "project_id": uuid4(), "run_id": uuid4()},
        )

    assert getattr(refused.value.orig, "sqlstate", None) == CHECK_VIOLATION


# ── roles (story 1) ─────────────────────────────────────────────────────────────────────


def test_an_unknown_role_is_refused_with_its_line(api: httpx.Client) -> None:
    name = f"e2e-metrics-{uuid4().hex}"

    response = api.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": ROLE_LEAF.format(name=name, role="build")}
    )

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    reasons = [(entry["line"], entry["reason"]) for entry in response.json()["errors"]]
    assert any(reason == "unknown role build" and line for line, reason in reasons), reasons


def test_a_declared_role_reaches_the_planned_row(
    api: httpx.Client, fixtures: Fixtures, settings: Settings, connection: Connection
) -> None:
    name = f"e2e-metrics-{uuid4().hex}"
    save(api, name, ROLE_LEAF.format(name=name, role="implement"))
    repository_id, _ = new_repository(api, fixtures, settings)
    run = start(api, name, repository_id)

    rows = connection.execute(
        text("select path, role from public.step_run where run_id = :run_id"),
        {"run_id": run["id"]},
    ).all()

    # the planner adds rows of its own, which declare no role
    assert [role for path, role in rows if path.endswith("touch")] == ["implement"]
    assert {role for path, role in rows if not path.endswith("touch")} <= {""}
    wait_for(api, run["id"], TERMINAL)


# ── the Run label (story 3) and the Run's own repository row (story 2) ──────────────────


def test_the_label_defaults_sets_restores_and_refuses(
    api: httpx.Client, fixtures: Fixtures, settings: Settings, connection: Connection
) -> None:
    name = f"e2e-metrics-{uuid4().hex}"
    save(api, name, ROLE_LEAF.format(name=name, role="verify"))
    repository_id, project_name = new_repository(api, fixtures, settings)
    run = start(api, name, repository_id)
    run_id = run["id"]
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00")).astimezone(UTC)
    default = f"{project_name} {name} {created:%Y-%m-%d %H:%M}"

    assert run["label"] == default
    assert run.get("label_set_by_operator", False) is False
    assert wait_for(api, run_id, TERMINAL) == "done"

    set_ = api.patch(f"{RUNS}/{run_id}", json={"label": "  snake round 2 · story session  "})
    assert set_.status_code == HTTP_OK, set_.text
    assert set_.json()["label"] == "snake round 2 · story session"
    assert set_.json()["label_set_by_operator"] is True
    assert set_.json()["status"] == "done"
    assert api.get(f"{RUNS}/{run_id}").json()["label"] == "snake round 2 · story session"

    for refused in ("x" * (MAX_LABEL + 1), "   "):
        response = api.patch(f"{RUNS}/{run_id}", json={"label": refused})
        assert response.status_code == HTTP_UNPROCESSABLE, response.text
        assert response.headers["content-type"].startswith("application/problem+json")

    restored = api.patch(f"{RUNS}/{run_id}", json={"label": None})
    assert restored.status_code == HTTP_OK, restored.text
    assert restored.json()["label"] == default
    assert restored.json().get("label_set_by_operator", False) is False

    paths = connection.execute(
        text("select path from public.run_repository where run_id = :run_id"),
        {"run_id": run_id},
    ).scalars()
    assert list(paths) == ["."]


def test_a_label_given_at_creation_is_the_operators(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    name = f"e2e-metrics-{uuid4().hex}"
    save(api, name, ROLE_LEAF.format(name=name, role="verify"))
    repository_id, _ = new_repository(api, fixtures, settings)

    run = start(api, name, repository_id, label="bench round 1")

    assert run["label"] == "bench round 1"
    assert run["label_set_by_operator"] is True
    wait_for(api, run["id"], TERMINAL)


# ── result versions and the calculation job (story 5) ───────────────────────────────────


def test_a_run_that_ends_gets_v1_and_a_manual_calculation_gets_v2(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    run_id = done_run(api, fixtures, settings)["id"]

    (v1,) = wait_for_version(api, run_id, 1)
    assert v1["entry_point"] == ["at_attempt_end"]
    first = api.get(f"{RUNS}/{run_id}/metrics", params={"v": 1})
    assert first.status_code == HTTP_OK, first.text
    assert first.json()["version"] == 1
    assert first.json()["values_so_far"] is False
    calculation = api.get(f"{RUNS}/{run_id}/metrics/calculations/1").json()
    assert calculation["state"] == "done"

    queued = api.post(f"{RUNS}/{run_id}/metrics/calculate")
    assert queued.status_code == HTTP_ACCEPTED, queued.text
    assert queued.json()["target_n"] == SECOND
    assert queued.json()["entry_point"] == ["manual"]

    versions = wait_for_version(api, run_id, 2)
    assert [version["n"] for version in versions] == [1, SECOND]
    assert versions[1]["entry_point"] == ["manual"]
    latest = api.get(f"{RUNS}/{run_id}/metrics").json()
    assert latest["version"] == SECOND
    assert latest["latest"] == SECOND
    # `latest` names the Run's newest version, so only it moves once v2 exists
    again = api.get(f"{RUNS}/{run_id}/metrics", params={"v": 1}).json()
    assert again == {**first.json(), "latest": SECOND}
    missing = api.get(f"{RUNS}/{run_id}/metrics", params={"v": 3})
    assert missing.status_code == HTTP_NOT_FOUND


def test_every_stored_value_carries_its_method_and_origin(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    run = done_run(api, fixtures, settings)
    wait_for_version(api, run["id"], 1)

    items = api.get(f"{RUNS}/{run['id']}/metrics", params={"v": 1}).json()["items"]

    for item in items:
        assert item["method_id"].startswith(f"{item['metric_id']}@"), item
        assert item["value_num"] is None or item["missing"] in (None, "partial"), item
        assert item["origin"] is not None, item
        assert item["origin"]["run_id"] == run["id"], item
        assert item["origin"]["template_name"] == run["template"], item


def test_a_live_run_reads_values_so_far_refuses_calculate_and_gets_v1_once_cancelled(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    name = f"e2e-metrics-{uuid4().hex}"
    save(api, name, TWO_STEP_TEMPLATE.format(name=name, branch=f"e2e-metrics-{uuid4().hex[:8]}"))
    repository_id, _ = new_repository(api, fixtures, settings)
    run_id = start(api, name, repository_id)["id"]
    try:
        wait_for(api, run_id, {"needs_you"})

        live = api.get(f"{RUNS}/{run_id}/metrics")
        assert live.status_code == HTTP_OK, live.text
        assert live.json()["values_so_far"] is True
        assert live.json()["version"] is None

        refused = api.post(f"{RUNS}/{run_id}/metrics/calculate")
        assert refused.status_code == HTTP_CONFLICT, refused.text
        assert refused.headers["content-type"].startswith("application/problem+json")
    finally:
        assert signal(api, run_id, "cancel", confirm=True).status_code == HTTP_OK

    (v1,) = wait_for_version(api, run_id, 1)
    assert v1["entry_point"] == ["at_attempt_end"]


# ── the gateway-read comparison (story 6) ───────────────────────────────────────────────


def test_the_gateway_reads_of_an_ended_run_are_listed_per_attempt(
    api: httpx.Client, fixtures: Fixtures, settings: Settings
) -> None:
    run_id = done_run(api, fixtures, settings)["id"]
    wait_for_version(api, run_id, 1)

    response = api.get(f"{RUNS}/{run_id}/metrics/gateway-reads")

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["next_cursor"] is None
    for item in body["items"]:
        UUID(item["attempt_id"])
        assert item["role"], item
        assert item["harness_usd"] is None or float(item["harness_usd"]) >= 0, item
        times = [read["read_at"] for read in item["reads"]]
        assert times == sorted(times), item
