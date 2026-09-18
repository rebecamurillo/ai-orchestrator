"""`retry_prompt` appears in `GET /runs/{id}/detail` when the template carries a retry block
(story 3-5).

The retry need not actually fire — `retry_prompt` is set at plan time onto `with_resolved`,
so the field is visible in the GET response as soon as any step row is planned, regardless of
whether a retry has occurred.

Requires `ORCH_TEST_MODE=1` on the stack (the same condition as `test_answer_signal.py`):
the `fake` harness must be available.  The test fails by name on that check rather than
timing out.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.gates_fixture import GatesFixture
from tests.e2e.test_run_creation import (
    RUNS,
    clone_check,
    create_project,
    create_repository,
)

HTTP_OK = 200
HTTP_CREATED = 201
TIMEOUT_SECONDS = 10.0
HARNESSES = "/api/v1/harnesses"
TEMPLATES = "/api/v1/templates"

#: The retry prompt text this test posts and then asserts in the GET response.
RETRY_PROMPT_TEXT = "expected-retry-prompt-text"

#: Minimal template with one agent step that has a retry block.
AGENT_TEMPLATE = """\
name: {name}
version: 1
description: retry-prompt e2e test fixture
inputs:
  project:
    type: project
    required: true
  repository:
    type: repository
    required: true
  base_branch:
    type: string
    required: true
steps:
  - id: build
    uses: agent
    gate: liveness
    retry:
      max: 1
      prompt: "{retry_prompt}"
"""

#: How long to poll for a step row to appear in the detail response.
RUN_TIMEOUT_SECONDS = 60.0
POLL_INTERVAL_SECONDS = 1.0


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    """Fail by name when the stack is not in test mode, rather than timing out later."""
    response = api.get(HARNESSES)
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def bmad_version() -> str:
    """The pin the fixture's manifest has to state for pre-flight to pass (AD-16)."""
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the gates fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def run_id(
    api: httpx.Client, settings: Settings, bmad_version: str, test_mode: None
) -> Iterator[str]:
    """A Run on a test-owned template with a retry block; cancelled on teardown."""
    fixtures = GatesFixture(settings.work_dir, bmad_version)
    project_id = create_project(api)
    url = fixtures.make()
    repository_id = create_repository(api, project_id, url)
    clone_check(api, repository_id)

    template_name = f"e2e-retry-prompt-{uuid4().hex}"
    saved = api.post(
        f"{TEMPLATES}/{template_name}/versions",
        json={"yaml": AGENT_TEMPLATE.format(name=template_name, retry_prompt=RETRY_PROMPT_TEXT)},
    )
    assert saved.status_code == HTTP_CREATED, saved.text

    started = api.post(
        RUNS,
        json={
            "template_name": template_name,
            "template_version": 1,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": "main",
            "budget_usd": "5",
            "harness": "fake",
            "inputs": {},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    rid = str(started.json()["run"]["id"])
    try:
        yield rid
    finally:
        api.post(f"{RUNS}/{rid}/signals", json={"kind": "cancel"})


def _poll_for_steps(api: httpx.Client, rid: str) -> list[dict[str, Any]]:
    """Poll `GET /runs/{id}/detail` until at least one step row appears."""
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        resp = api.get(f"{RUNS}/{rid}/detail")
        assert resp.status_code == HTTP_OK, resp.text
        steps: list[dict[str, Any]] = resp.json().get("steps", [])
        if steps:
            return steps
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(
        f"run {rid} had no step rows after {RUN_TIMEOUT_SECONDS:.0f}s — "
        "the fake harness may not have planned the run"
    )


def test_retry_prompt_appears_in_step_detail(api: httpx.Client, run_id: str) -> None:
    steps = _poll_for_steps(api, run_id)

    agent_steps = [s for s in steps if s.get("kind") == "agent"]
    assert agent_steps, f"no agent step rows found in: {steps}"
    assert agent_steps[0]["retry_prompt"] == RETRY_PROMPT_TEXT, agent_steps[0]
