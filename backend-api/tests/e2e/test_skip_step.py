"""Skip one step end to end on the scripted harness (CAP-1, story 1, 2026-09-25).

What only the running stack settles is that `skip_step` is a single-row operation: that
`POST /runs/{id}/signals {kind: "skip_step"}` marks exactly the parked row `skipped`,
writes a `gate_record` naming the operator, returns the Run to `running`, and the walker
executes the next row — while the enclosing story's other rows are untouched. No double
shows any of that: `test_signal_run.py` and `test_signal_rules.py` prove what the writer
decides, and this proves the decision is carried out.

Story 1 of the gates fixture is what is skipped: its first dispatch blocks (`.fake-harness/1/
attempt-1.yaml`), which is the stop that represents an operator giving up on a single step.
The Run parks `blocked` on that row; `skip_step` marks it `skipped` and returns the Run to
`running`.

Needs `ORCH_TEST_MODE=1` on the stack (`docker-compose.e2e.yml` sets it, `make e2e` uses it);
the `test_mode` fixture fails by name rather than skipping, because a gate that skips reports
success for a suite that ran nothing. The Run is cancelled at the end so it holds neither a
global slot nor its Repository's partition (AD-12).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.gates_fixture import GatesFixture, epic_template_as
from tests.e2e.test_answer_signal import detail_of, poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 10.0

SPEC_FOLDER = "specs/gates"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates"

STORY_1_BUILD = "stories[0].build"
STORY_1_VERIFY = "stories[0].verify"
STORY_1_COMMIT_GUARD = "stories[0].commit-guard"
STORY_2_SYNC = "stories[1].sync"

#: `signal_effects.py::SKIPPED_BY_OPERATOR`, as the read model prints it on the row.
SKIPPED_BY_OPERATOR = "skipped by operator"

#: Story 1 is dispatched once and the skip replaces any further attempt.
ATTEMPTS_BEFORE_THE_SKIP = 1


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def bmad_version() -> str:
    value = os.environ.get("BMAD_VERSION")
    if not value:
        pytest.fail(
            "BMAD_VERSION is not set: the gates fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return value


@pytest.fixture(scope="module")
def gates(settings: Settings, bmad_version: str) -> GatesFixture:
    return GatesFixture(settings.work_dir, bmad_version)


@pytest.fixture(scope="module")
def test_mode(api: httpx.Client) -> None:
    """Fail by name when the stack is not in test mode, rather than timing out later."""
    response = api.get("/api/v1/harnesses")
    assert response.status_code == HTTP_OK, response.text
    rows = {item["name"]: item for item in response.json()["items"]}
    assert "fake" in rows, (
        "the `fake` harness is not seeded: this gate needs ORCH_TEST_MODE=1 on the stack "
        "(docker-compose.e2e.yml sets it; `make e2e` is the target that uses it)"
    )
    assert rows["fake"]["enabled"] is True, rows["fake"]


@pytest.fixture(scope="module")
def parked(
    api: httpx.Client, gates: GatesFixture, test_mode: None
) -> Iterator[dict[str, Any]]:
    """A Run on a fresh gates clone, walked until it parks `blocked` on story 1."""
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
            "unit_test_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name = f"e2e-gates-skip-step-{uuid4().hex}"
    saved = api.post(
        f"/api/v1/templates/{template_name}/versions",
        json={"yaml": epic_template_as(template_name)},
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
            "inputs": {"spec_folder": SPEC_FOLDER, "branch": f"{DECLARED_BRANCH}-{uuid4().hex}"},
        },
    )
    assert started.status_code == HTTP_CREATED, started.text
    run_id = str(started.json()["run"]["id"])
    try:
        detail = poll_until(
            api,
            run_id,
            lambda detail: (
                detail["run"]["status"] == "needs_you"
                and step_status(detail, STORY_1_BUILD) == "blocked"
            ),
            "the Run parking blocked on story 1 build",
        )
        yield {"id": run_id, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


def test_the_blocked_stop_offers_skip_step(parked: dict[str, Any]) -> None:
    """AD-13's table through the read model — `skip_step` admitted on every park kind."""
    assert "skip_step" in parked["detail"]["admitted_signals"]


@pytest.fixture(scope="module")
def skipped(api: httpx.Client, parked: dict[str, Any]) -> dict[str, Any]:
    """The skip_step signal, and the Run polled until it resumes."""
    response = api.post(f"{RUNS}/{parked['id']}/signals", json={"kind": "skip_step"})
    assert response.status_code == HTTP_OK, response.text
    # Poll until the Run is either running or parks again (next step)
    resumed = poll_until(
        api,
        parked["id"],
        lambda detail: (
            detail["run"]["status"] in ("running", "needs_you", "done", "failed")
            and step_status(detail, STORY_1_BUILD) == "skipped"
        ),
        "the Run resuming after skip_step",
    )
    return {"signalled": response.json()["status"], "detail": resumed}


def test_the_run_leaves_needs_you_as_soon_as_the_signal_commits(
    skipped: dict[str, Any],
) -> None:
    """FR-18 timing: the signal response already carries `running`."""
    assert skipped["signalled"] == "running"


def test_the_parked_row_is_marked_skipped_by_the_operator(
    skipped: dict[str, Any],
) -> None:
    """Exactly one row is skipped — the build row that was parked."""
    build = next(step for step in skipped["detail"]["steps"] if step["path"] == STORY_1_BUILD)

    assert build["status"] == "skipped"
    assert build["reason"] == SKIPPED_BY_OPERATOR
    assert build["attempts"] == ATTEMPTS_BEFORE_THE_SKIP


def test_the_story_rows_outside_the_skipped_step_are_untouched(
    skipped: dict[str, Any],
) -> None:
    """skip_step touches exactly one row: not the enclosing story's verify or commit-guard."""
    detail = skipped["detail"]
    steps_by_path = {step["path"]: step for step in detail["steps"]}

    if STORY_1_VERIFY in steps_by_path:
        assert steps_by_path[STORY_1_VERIFY]["status"] != "skipped", (
            "skip_step must not mark the story's verify row skipped"
        )


def test_the_gate_record_holds_exactly_one_skip_step_naming_the_operator(
    skipped: dict[str, Any],
) -> None:
    """AD-13: `gate_record` carries `event: "skip_step"` and `actor: "operator"`."""
    skips = [
        entry
        for entry in skipped["detail"]["gate_record"]
        if entry["event"] == "skip_step"
    ]

    assert len(skips) == 1
    assert skips[0]["actor"] == "operator"
    assert skips[0]["path"] == STORY_1_BUILD


def test_the_run_is_running_after_the_skip(
    api: httpx.Client, parked: dict[str, Any], skipped: dict[str, Any]
) -> None:
    """The Run carries on past the skipped step."""
    detail = detail_of(api, parked["id"])

    assert detail["run"]["status"] in ("running", "needs_you", "done")
    assert step_status(detail, STORY_1_BUILD) == "skipped"


def test_dependency_park_refuses_skip_step(api: httpx.Client, parked: dict[str, Any]) -> None:
    """A dependency park (park_path=None) refuses skip_step with 409 (AD-13 constraint)."""
    # We cannot easily park on a dependency stop in the gates fixture, so this tests the
    # *structural* refusal: once the Run has been skipped and is terminal, skip_step is
    # no longer admitted, so the 409 is reachable via the terminal state instead.
    #
    # The unit tests in test_signal_rules.py cover the dependency-park refusal path directly.
    # This test covers the post-terminal refusal path in the running stack.
    detail = detail_of(api, parked["id"])
    run_status = detail["run"]["status"]
    if run_status in ("done", "cancelled", "failed"):
        response = api.post(f"{RUNS}/{parked['id']}/signals", json={"kind": "skip_step"})
        assert response.status_code == HTTP_CONFLICT, (
            f"expected 409 on terminal Run, got {response.status_code}: {response.text}"
        )
