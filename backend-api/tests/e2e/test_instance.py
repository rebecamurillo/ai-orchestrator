"""The instance hold, the activity read and the setup-record fields against the running stack
(orchestrator-deploy-folder epic 1: SPEC CAP-2, CAP-3, CAP-4; member AD-29, AD-30).

The rules are proven over fakes in the unit suite; what only the running stack settles is
that the real walker, inside its real `attempt_row` engine step, waits on a hold written
through real HTTP into a real Postgres, and that the activity read sees a step the real
engine is actually running.

**The hold is instance-wide.** Every test that places one releases it in `finally`, with a
short `ttl_seconds` as the second line of defence, so no later module finds the instance held.
Every Run this module starts is cancelled or finished before its test returns.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import Fixtures, manifest_stating
from tests.e2e.test_run_creation import (
    RUNS,
    TEMPLATES,
    clone_check,
    create_project,
    create_repository,
    project_id_of,
    run_payload,
)

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_UNAUTHORIZED = 401
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422

ACTIVITY = "/api/v1/instance/activity"
HOLD = "/api/v1/instance/hold"
QUEUE = "/api/v1/queue"
HARNESSES = "/api/v1/harnesses"
VERSION = "/api/v1/version"

TIMEOUT_SECONDS = 10.0
WALK_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5
#: The walker polls a hold every 5 s; a Run held this long has had several chances to start.
HELD_OBSERVATION_SECONDS = 8.0
#: The hold's own expiry, short so a test that dies before its `finally` frees the instance.
HOLD_TTL_SECONDS = 120
#: Clock tolerance between `held_at + ttl` and `expires_at` (both written by the server).
EXPIRY_TOLERANCE = timedelta(seconds=2)

HELD_FOR_UPGRADE = "held for upgrade"

SHELL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e instance {kind}\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: {step}\n"
    "    uses: shell\n"
    "    with: {{ command: '{command}' }}\n"
    "    gate: deterministic\n"
)
#: Long enough for the test to read it as working, short enough not to outlive the module.
SLOW_STEP, SLOW_COMMAND = "linger", "sleep 30"
FAST_STEP, FAST_COMMAND = "touch", "true"


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture
def repository_id(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    """A Repository of its own per test, so no Run here waits behind another's branch."""
    project_id = create_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(api, project_id, url)
    clone_check(api, repository)
    return repository


@pytest.fixture
def released(api: httpx.Client) -> Iterator[None]:
    """Whatever the test does, the instance is not held after it."""
    try:
        yield
    finally:
        response = api.delete(HOLD)
        assert response.status_code == HTTP_NO_CONTENT, response.text


def parse(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def activity(api: httpx.Client) -> dict[str, Any]:
    response = api.get(ACTIVITY)
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def start_shell_run(api: httpx.Client, repository_id: str, step: str, command: str) -> str:
    name = f"e2e-instance-{uuid4().hex}"
    yaml = SHELL_TEMPLATE.format(name=name, kind=step, step=step, command=command)
    saved = api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": yaml})
    assert saved.status_code == HTTP_CREATED, saved.text
    payload = run_payload(name, repository_id, project_id=project_id_of(api, repository_id))
    created = api.post(RUNS, json=payload)
    assert created.status_code == HTTP_CREATED, created.text
    return str(created.json()["run"]["id"])


def detail_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def step_of(api: httpx.Client, run_id: str, step: str) -> dict[str, Any]:
    steps = detail_of(api, run_id)["steps"]
    found = next((row for row in steps if str(row["path"]).split("/")[-1] == step), None)
    assert found is not None, steps
    return dict(found)


def status_of(api: httpx.Client, run_id: str) -> str:
    response = api.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def wait_until(what: str, done: Any) -> None:
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if done():
            return
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"{what} did not happen within {WALK_TIMEOUT_SECONDS:.0f}s")


def cancel(api: httpx.Client, run_id: str) -> None:
    response = api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {}})
    assert response.status_code == HTTP_OK, response.text


def working_entry(api: httpx.Client, run_id: str) -> dict[str, Any] | None:
    return next((w for w in activity(api)["working"] if w["run_id"] == run_id), None)


def working_on(api: httpx.Client, run_id: str, step: str) -> bool:
    # row 1 (`plan.check`) is working first; wait for the named step (PR #19, 2026-11-12: race)
    entry = working_entry(api, run_id)
    return entry is not None and str(entry["path"]).split("/")[-1] == step


# ── the bearer guards every new route ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", ACTIVITY), ("POST", HOLD), ("DELETE", HOLD)],
)
def test_every_instance_route_refuses_without_the_bearer(
    client: httpx.Client, method: str, path: str
) -> None:
    response = client.request(method, path, json={"ttl_seconds": 60, "reason": "e2e"})

    assert response.status_code == HTTP_UNAUTHORIZED, response.text


# ── CAP-3: the activity read ────────────────────────────────────────────────────────────


def test_the_activity_read_has_its_four_fields_and_the_pinned_engine_version(
    api: httpx.Client,
) -> None:
    body = activity(api)

    assert set(body) == {"working", "in_engine", "hold", "dbos_application_version"}
    assert isinstance(body["working"], list)
    assert isinstance(body["in_engine"], list)
    expected = os.environ.get("DBOS_APPLICATION_VERSION", "1")
    assert body["dbos_application_version"] == expected


def test_a_running_shell_step_is_working_and_its_run_is_in_the_engine(
    api: httpx.Client, repository_id: str
) -> None:
    run_id = start_shell_run(api, repository_id, SLOW_STEP, SLOW_COMMAND)
    try:
        wait_until(
            f"run {run_id} working on {SLOW_STEP}", lambda: working_on(api, run_id, SLOW_STEP)
        )

        entry = working_entry(api, run_id)
        assert entry is not None
        assert entry["kind"] == "shell"
        assert str(entry["path"]).split("/")[-1] == SLOW_STEP
        assert entry["run_label"]
        assert entry["started_at"] is not None

        engine = next((r for r in activity(api)["in_engine"] if r["run_id"] == run_id), None)
        assert engine is not None, "a running Run must be listed under in_engine"
        assert engine["status"] == "running"
    finally:
        cancel(api, run_id)
        wait_until(f"run {run_id} cancelled", lambda: status_of(api, run_id) == "cancelled")

    after = activity(api)
    assert all(w["run_id"] != run_id for w in after["working"])
    assert all(r["run_id"] != run_id for r in after["in_engine"]), "a terminal Run is listed"


# ── CAP-4: the hold's request rules ─────────────────────────────────────────────────────


@pytest.mark.parametrize("ttl", [0, 3601])
def test_a_ttl_outside_one_to_3600_is_422_and_holds_nothing(api: httpx.Client, ttl: int) -> None:
    response = api.post(HOLD, json={"ttl_seconds": ttl, "reason": "e2e out of range"})

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    assert response.headers["content-type"].startswith("application/problem+json")
    assert activity(api)["hold"] is None


def test_a_reason_over_200_characters_is_422(api: httpx.Client) -> None:
    response = api.post(HOLD, json={"ttl_seconds": 60, "reason": "x" * 201})

    assert response.status_code == HTTP_UNPROCESSABLE, response.text


def test_delete_is_204_when_nothing_is_held(api: httpx.Client) -> None:
    assert api.delete(HOLD).status_code == HTTP_NO_CONTENT
    assert api.delete(HOLD).status_code == HTTP_NO_CONTENT
    assert activity(api)["hold"] is None


# ── CAP-4: place, read back, replace, release ───────────────────────────────────────────


def test_a_hold_is_placed_read_back_replaced_and_released(
    api: httpx.Client, released: None
) -> None:
    placed = api.post(HOLD, json={"ttl_seconds": HOLD_TTL_SECONDS, "reason": "e2e upgrade"})

    assert placed.status_code == HTTP_CREATED, placed.text
    hold = placed.json()
    assert set(hold) == {"held_at", "expires_at", "reason"}
    assert hold["reason"] == "e2e upgrade"
    expected = parse(hold["held_at"]) + timedelta(seconds=HOLD_TTL_SECONDS)
    assert abs(parse(hold["expires_at"]) - expected) <= EXPIRY_TOLERANCE

    assert activity(api)["hold"] == hold

    replaced = api.post(HOLD, json={"ttl_seconds": HOLD_TTL_SECONDS // 2, "reason": "again"})
    assert replaced.status_code == HTTP_CREATED, replaced.text
    assert parse(replaced.json()["expires_at"]) < parse(hold["expires_at"])
    assert activity(api)["hold"]["reason"] == "again"

    assert api.delete(HOLD).status_code == HTTP_NO_CONTENT
    assert activity(api)["hold"] is None


def test_a_hold_is_refused_409_naming_the_working_step_and_nothing_is_held(
    api: httpx.Client, repository_id: str, released: None
) -> None:
    run_id = start_shell_run(api, repository_id, SLOW_STEP, SLOW_COMMAND)
    try:
        wait_until(
            f"run {run_id} working on {SLOW_STEP}", lambda: working_on(api, run_id, SLOW_STEP)
        )

        refused = api.post(HOLD, json={"ttl_seconds": HOLD_TTL_SECONDS, "reason": "e2e"})

        assert refused.status_code == HTTP_CONFLICT, refused.text
        assert refused.headers["content-type"].startswith("application/problem+json")
        problem = refused.json()
        assert problem["status"] == HTTP_CONFLICT
        named = next((e for e in problem["errors"] if e["run_id"] == run_id), None)
        assert named is not None, problem
        assert set(named) == {"run_id", "run_label", "path", "kind", "started_at"}
        assert named["kind"] == "shell"
        assert str(named["path"]).split("/")[-1] == SLOW_STEP
        assert activity(api)["hold"] is None, "a refused hold must write nothing"
    finally:
        cancel(api, run_id)
        wait_until(f"run {run_id} cancelled", lambda: status_of(api, run_id) == "cancelled")


# ── CAP-4 / D-4: a held instance starts no step; release lets the Run finish ─────────────


def test_a_run_started_under_a_hold_waits_queued_then_finishes_after_release(
    api: httpx.Client, repository_id: str, released: None
) -> None:
    # Revised: a running metrics calculation is a working step against a hold (run-metrics
    # epic 2 story 5, 2026-11-13); the Runs earlier tests ended may still be calculating.
    wait_until(
        "earlier Runs' calculations to end",
        lambda: not any(w.get("kind") == "calculation" for w in activity(api)["working"]),
    )
    placed = api.post(HOLD, json={"ttl_seconds": HOLD_TTL_SECONDS, "reason": "e2e upgrade"})
    assert placed.status_code == HTTP_CREATED, placed.text

    run_id = start_shell_run(api, repository_id, FAST_STEP, FAST_COMMAND)
    try:
        time.sleep(HELD_OBSERVATION_SECONDS)

        # row 1 (`plan.check`) is the one held; FAST_STEP stays `planned` (PR #19, 2026-11-12)
        rows = sorted(detail_of(api, run_id)["steps"], key=lambda row: row["seq"])
        assert rows[0]["status"] == "queued", rows
        assert all(row["status"] in {"planned", "queued"} for row in rows), rows
        assert status_of(api, run_id) == "queued", "no attempt started, so the Run never ran"
        assert working_entry(api, run_id) is None

        queued = api.get(QUEUE)
        assert queued.status_code == HTTP_OK, queued.text
        item = next((i for i in queued.json()["items"] if i["run"]["id"] == run_id), None)
        assert item is not None, "a held running Run must stay in the queue"
        assert item["reason"] == HELD_FOR_UPGRADE

        assert api.delete(HOLD).status_code == HTTP_NO_CONTENT

        wait_until(f"run {run_id} done after release", lambda: status_of(api, run_id) == "done")
        assert step_of(api, run_id, FAST_STEP)["status"] == "done"
    finally:
        if status_of(api, run_id) not in {"done", "failed", "cancelled"}:
            cancel(api, run_id)


# ── CAP-2: the setup record fields on a stack no setup run has touched ──────────────────


def test_every_harness_item_carries_setup_null_without_a_setup_record(api: httpx.Client) -> None:
    """The backend never writes `setup-run.json`; this stack's image ships none, so the
    field is present and null on every item, never absent and never a 500."""
    response = api.get(HARNESSES)

    assert response.status_code == HTTP_OK, response.text
    items = response.json()["items"]
    assert items
    for item in items:
        assert "setup" in item, item
        assert item["setup"] is None, item


def test_the_version_read_carries_bmad_installed_null_and_keeps_bmad_version(
    api: httpx.Client, settings: Settings
) -> None:
    response = api.get(VERSION)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert "bmad_installed" in body
    assert body["bmad_installed"] is None
    assert body["bmad_version"] == settings.bmad_version
