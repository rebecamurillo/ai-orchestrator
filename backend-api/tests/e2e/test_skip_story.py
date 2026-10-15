"""Skip story and its re-baseline, end to end on the scripted harness (6.4, SPEC CAP-4).

What only the running stack settles is that the skip is a *loop*, not a set of row writes:
that `POST /runs/{id}/signals` marks the frame's remaining rows skipped and wakes the walker,
that the frame's `verify` row then really re-runs the repository's own quality gate against
the tree as it stands, that its commit guard runs afterwards with the Operator's own message
resolved into it, and that the next Story starts from a green, committed tree. No double
shows any of that: `test_signal_run.py` and `tests/unit/application/test_skip_story_signal.py`
prove what the writer decides, and this proves the decision is carried out.

Story 1 of the gates fixture is what is skipped: its first dispatch blocks (`.fake-harness/1/
attempt-1.yaml`), which is the stop FR-20's own success signal describes an Operator giving
up at. `check.sh` passes against the committed `GATE_OK`, so the re-baseline is green and
the Run walks on to story 2 — the "leftovers are committed, nothing half-done leaks into the
next story" half of the story's own intent.

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
from tests.e2e.helpers.gates_fixture import GatesFixture
from tests.e2e.helpers.templates import save_epic_pair
from tests.e2e.test_answer_signal import detail_of, poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
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

#: Story 1 is dispatched once and never again: the skip is what replaces the second attempt.
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
def parked(api: httpx.Client, gates: GatesFixture, test_mode: None) -> Iterator[dict[str, Any]]:
    """A Run on a fresh gates clone, walked until it parks `blocked` on story 1."""
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
            # operator revision 2026-09-15: since the quality-gate reorder (b0f3898) the
            # story's verify row runs `unit_test_command`; declaring it keeps verify
            # exercised — without it the row plans `skipped · no command`.
            "unit_test_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name, _ = save_epic_pair(api, "e2e-gates-skip")

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
            "the Run parking blocked on story 1",
        )
        yield {"id": run_id, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


def test_the_blocked_stop_offers_skip_story(parked: dict[str, Any]) -> None:
    """AD-13's table through the read model the *Skip story* button reads (PRD §4.6)."""
    assert "skip_story" in parked["detail"]["admitted_signals"]


@pytest.fixture(scope="module")
def skipped(api: httpx.Client, parked: dict[str, Any]) -> dict[str, Any]:
    """The skip, and the Run walked on until story 1's commit guard has run."""
    response = api.post(f"{RUNS}/{parked['id']}/signals", json={"kind": "skip_story"})
    assert response.status_code == HTTP_OK, response.text
    resumed = poll_until(
        api,
        parked["id"],
        lambda detail: step_status(detail, STORY_1_COMMIT_GUARD) in ("done", "error"),
        "story 1's commit guard running after the skip",
    )
    return {"signalled": response.json()["status"], "detail": resumed}


def test_the_run_leaves_needs_you_as_soon_as_the_signal_commits(skipped: dict[str, Any]) -> None:
    """The same timing FR-18 states for the Answer: the response already says `running`."""
    assert skipped["signalled"] == "running"


def test_the_story_that_was_given_up_on_is_marked_skipped_by_the_operator(
    skipped: dict[str, Any],
) -> None:
    build = next(step for step in skipped["detail"]["steps"] if step["path"] == STORY_1_BUILD)

    assert build["status"] == "skipped"
    assert build["reason"] == SKIPPED_BY_OPERATOR
    assert build["attempts"] == ATTEMPTS_BEFORE_THE_SKIP


def test_the_frames_verify_ran_as_the_re_baseline_and_passed(skipped: dict[str, Any]) -> None:
    """The quality gate is re-run against the tree the skip leaves — the whole point of the
    re-baseline, and the only thing that makes skipping honest for the *next* Story."""
    assert step_status(skipped["detail"], STORY_1_VERIFY) == "done"


def test_the_commit_guard_ran_and_the_next_story_started(skipped: dict[str, Any]) -> None:
    assert step_status(skipped["detail"], STORY_1_COMMIT_GUARD) == "done"
    assert step_status(skipped["detail"], STORY_2_SYNC) != "planned"


def test_the_gate_record_holds_exactly_one_skip_naming_the_operator(
    skipped: dict[str, Any],
) -> None:
    skips = [entry for entry in skipped["detail"]["gate_record"] if entry["event"] == "skip_story"]

    assert len(skips) == 1
    assert skips[0]["actor"] == "operator"
    assert skips[0]["path"] == STORY_1_BUILD


def test_the_run_carries_on_past_the_skipped_story(
    api: httpx.Client, parked: dict[str, Any], skipped: dict[str, Any]
) -> None:
    """Nothing half-done leaks into the next Story: the Run is running again, on story 2."""
    detail = detail_of(api, parked["id"])

    assert detail["run"]["status"] in ("running", "needs_you")
    assert step_status(detail, STORY_1_BUILD) == "skipped"
