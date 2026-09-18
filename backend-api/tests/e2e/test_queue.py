"""`GET /api/v1/queue` against the real engine (SPEC CAP-11, FR-13, FR-25), and the two
scheduled jobs' own registration (AC5: DBOS lists them with their configured crons).

The join itself is `tests/unit/application/test_queue.py`'s; what only the running stack
settles is that `GET /queue` reads the *real* durable engine's `list_queue()` — a genuinely
parked Run and a genuinely enqueued one behind it, both through real HTTP and a real
Postgres — and that `main.run_migrations`'s `schedule_jobs` step really registered
`clone_check` and `worktree_gc` with DBOS at start-up.

**This module cleans up after itself.** Both Runs it creates are cancelled once the queue
assertions are made, the way `test_signals.py`'s own docstring asks of every module after
it: nothing here holds a slot for the rest of the stack's life.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import create_engine_from, create_session_factory
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
NEEDS_YOU = "needs_you"
CANCELLED = "cancelled"
QUEUE = "/api/v1/queue"

WALK_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 0.5
#: The suite's own client timeout, matching `tests/e2e/conftest.py`.
TIMEOUT_SECONDS = 10.0

#: One `checkpoint` step: parks on its first execution and holds its slot indefinitely,
#: the same reason `test_engine_walker.py::CHECKPOINT_TEMPLATE` exists — a Run this test
#: needs to still find in the queue, not one that raced to `done` before it could ask.
CHECKPOINT_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: e2e queue checkpoint\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: pause\n"
    "    uses: checkpoint\n"
    "    gate: human\n"
)


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    """A module-scoped client: every Run this module creates is shared across assertions,
    the same reason `test_engine_walker.py::api` is module-scoped rather than the
    function-scoped `authenticated` fixture `tests/e2e/conftest.py` hands most modules."""
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def repository_id(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    project_id = create_project(api)
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository = create_repository(api, project_id, url)
    clone_check(api, repository)
    return repository


def save_checkpoint_template(client: httpx.Client, name: str) -> None:
    response = client.post(
        f"{TEMPLATES}/{name}/versions", json={"yaml": CHECKPOINT_TEMPLATE.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text


def start_run(client: httpx.Client, repository_id: str) -> dict[str, Any]:
    name = f"e2e-queue-{uuid4().hex}"
    save_checkpoint_template(client, name)
    payload = run_payload(name, repository_id, project_id=project_id_of(client, repository_id))
    response = client.post(RUNS, json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


def status_of(client: httpx.Client, run_id: str) -> str:
    response = client.get(f"{RUNS}/{run_id}")
    assert response.status_code == HTTP_OK, response.text
    return str(response.json()["status"])


def wait_for(client: httpx.Client, run_id: str, target: str) -> None:
    deadline = time.monotonic() + WALK_TIMEOUT_SECONDS
    status = status_of(client, run_id)
    while status != target and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        status = status_of(client, run_id)
    if status != target:
        pytest.fail(f"run {run_id} did not reach {target!r} within {WALK_TIMEOUT_SECONDS:.0f}s")


def cancel(client: httpx.Client, run_id: str) -> None:
    response = client.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {}})
    assert response.status_code == HTTP_OK, response.text


def queue_row(client: httpx.Client, run_id: str) -> dict[str, Any] | None:
    response = client.get(QUEUE)
    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    return next((item for item in body["items"] if item["run"]["id"] == run_id), None)


def test_max_active_runs_reads_off_settings(api: httpx.Client, settings: Settings) -> None:
    response = api.get(QUEUE)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["next_cursor"] is None
    assert body["max_active_runs"] == settings.max_active_runs


def test_a_parked_run_and_the_one_queued_behind_it_read_the_fixed_reasons(
    api: httpx.Client, repository_id: str
) -> None:
    """AD-12: a Run parked on a real `checkpoint` row holds its Repository's partition, and
    a second Run against that Repository waits behind it — both through the real engine."""
    first = start_run(api, repository_id)
    first_id = str(first["run"]["id"])
    wait_for(api, first_id, NEEDS_YOU)

    second = start_run(api, repository_id)
    second_id = str(second["run"]["id"])
    assert second["starts_now"] is False

    try:
        parked_row = queue_row(api, first_id)
        assert parked_row is not None, "the parked run is not in the queue"
        assert parked_row["reason"] == "waiting for your answer"
        assert parked_row["position"] is None

        waiting_row = queue_row(api, second_id)
        assert waiting_row is not None, "the waiting run is not in the queue"
        # story 5-1 (2026-09-17): the queue partitions per branch, not per repository, and
        # the reason follows — `branch held by {run} · {branch}` replaced the repository lock.
        assert waiting_row["reason"].startswith("branch held by ")
        assert isinstance(waiting_row["position"], int)
    finally:
        cancel(api, first_id)
        wait_for(api, second_id, NEEDS_YOU)
        cancel(api, second_id)
        assert status_of(api, first_id) == CANCELLED
        assert status_of(api, second_id) == CANCELLED


# ── AC5: both scheduled jobs are registered with the configured crons ───────────────────


def test_both_jobs_are_registered_with_their_configured_crons(settings: Settings) -> None:
    engine = create_engine_from(settings)
    try:
        session_factory = create_session_factory(engine)
        with session_factory() as session:
            rows = session.execute(
                text(
                    "select schedule_name, schedule from dbos.workflow_schedules "
                    "where schedule_name in ('clone_check', 'worktree_gc')"
                )
            ).all()
    finally:
        engine.dispose()

    crons = {name: cron for name, cron in rows}
    assert crons == {
        "clone_check": settings.clone_check_cron,
        "worktree_gc": settings.worktree_gc_cron,
    }
