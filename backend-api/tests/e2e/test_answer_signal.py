"""UJ-3's first gate, end to end on the scripted harness: blocked → Answer → done (CAP-1).

Everything the Answer *decides* is proven over fakes in the unit suite. What only the running
stack settles is that the whole loop is real: that a Run parks `blocked` because a coding
agent wrote a Story file saying so, that `POST /runs/{id}/signals` takes the Operator's
paragraph and the walker wakes up, that the executor archives the file and re-dispatches, and
that the branch afterwards holds the archived question with the answer under it, the new Story
file, and the work — none of which any double can show.

**It runs on the `fake` harness** (AR-14), which needs `ORCH_TEST_MODE=1` on the stack.
`docker-compose.e2e.yml` sets it, so `make e2e` has it; a stack without it fails the first
assertion below by name rather than skipping, because a gate that skips reports success for a
suite that ran nothing.

This module cancels its Run at the end, so it holds neither a global slot nor its Repository's
partition afterwards (AD-12) — the same discipline `test_repo_init.py` keeps by finishing.
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
from tests.e2e.helpers.gates_fixture import GatesFixture, epic_template_as
from tests.e2e.test_run_creation import (
    PROJECTS,
    RUNS,
    clone_check,
    create_project,
)

HTTP_OK = 200
HTTP_CREATED = 201
TIMEOUT_SECONDS = 10.0

#: The fixture's own spec folder, quality gate and the branch this Run works on.
SPEC_FOLDER = "specs/gates"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates"

#: The Story the Answer resumes, its rows, and the files the scenarios leave behind.
STORY_ID = "1"
BUILD = "stories[0].build"
COMMIT_GUARD = "stories[0].commit-guard"
STORY_FILE = f"{SPEC_FOLDER}/stories/{STORY_ID}-notify.md"
ARCHIVED = f"{SPEC_FOLDER}/stories/.answers/{STORY_ID}-attempt-1.md"
WORK_FILE = "NOTIFY.md"

#: Attempt 1 blocks, attempt 2 finishes: the Answer is what makes the second one happen.
ATTEMPTS_AFTER_THE_ANSWER = 2

CONDITION = "intent gap"
ANSWER = "Post to the project's channel only"

#: The clause FR-18 puts on the end of the re-dispatch's prompt, verbatim.
ANSWER_CLAUSE = f'Answer from the operator to the blocking condition "{CONDITION}": {ANSWER}'

#: The scripted harness is fast, but a Run still walks a plan through a durable engine.
RUN_TIMEOUT_SECONDS = 300.0
POLL_INTERVAL_SECONDS = 1.0


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


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
    """A Run on the gates fixture, walked until it parks `blocked` on story 1."""
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

    template_name = f"e2e-gates-{uuid4().hex}"
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
        yield {"id": run_id, "detail": wait_for_park(api, run_id)}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


def detail_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def step_status(detail: dict[str, Any], path: str) -> str | None:
    return next((step["status"] for step in detail["steps"] if step["path"] == path), None)


def poll_until(api: httpx.Client, run_id: str, done: Any, what: str) -> dict[str, Any]:
    """Poll the detail until `done(detail)`, or fail naming the deadline and the last state."""
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    detail = detail_of(api, run_id)
    while time.monotonic() < deadline:
        if done(detail):
            return detail
        time.sleep(POLL_INTERVAL_SECONDS)
        detail = detail_of(api, run_id)
    alert = detail["alert"] or {}
    pytest.fail(
        f"{what} did not happen within {RUN_TIMEOUT_SECONDS:.0f}s — the Run is "
        f"{detail['run']['status']} at {alert.get('park_kind')}: {alert.get('reason')}; "
        f"rows: {[(step['path'], step['status']) for step in detail['steps']]}"
    )


def wait_for_park(api: httpx.Client, run_id: str) -> dict[str, Any]:
    return poll_until(
        api,
        run_id,
        lambda detail: (
            detail["run"]["status"] == "needs_you" and step_status(detail, BUILD) == "blocked"
        ),
        "the Run parking blocked on story 1",
    )


# ── the park ────────────────────────────────────────────────────────────────────────────


def test_the_run_parks_blocked_with_the_agents_own_question(parked: dict[str, Any]) -> None:
    """The stop the Operator sees: the park kind, and the agent's own words under it —
    `alert.reason` is the `## Auto Run Result` section the scripted harness wrote."""
    detail = parked["detail"]

    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "blocked"
    assert CONDITION in detail["alert"]["reason"]
    assert [entry["path"] for entry in detail["gate_record"] if entry["event"] == "blocked"] == [
        BUILD
    ]


def test_the_park_admits_the_answer(parked: dict[str, Any]) -> None:
    """AD-13's table, through the read model the Answer box reads (FR-18, UX-DR10)."""
    assert "answer" in parked["detail"]["admitted_signals"]


# ── the answer ──────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def answered(api: httpx.Client, parked: dict[str, Any]) -> dict[str, Any]:
    """The Answer, and the Run walked on until story 1's commit guard has run."""
    response = api.post(
        f"{RUNS}/{parked['id']}/signals",
        json={"kind": "answer", "payload": {"text": ANSWER}},
    )
    assert response.status_code == HTTP_OK, response.text
    left_needs_you = response.json()["status"]
    resumed = poll_until(
        api,
        parked["id"],
        lambda detail: step_status(detail, COMMIT_GUARD) == "done",
        "story 1 reaching its commit guard after the Answer",
    )
    return {"signalled": left_needs_you, "detail": resumed}


def test_the_run_leaves_needs_you_as_soon_as_the_signal_commits(answered: dict[str, Any]) -> None:
    """FR-18's timing: the response already says `running`, before any executor has run."""
    assert answered["signalled"] == "running"


def test_the_gate_record_holds_the_answer_and_the_operators_own_words(
    answered: dict[str, Any],
) -> None:
    answers = [entry for entry in answered["detail"]["gate_record"] if entry["event"] == "answer"]

    assert len(answers) == 1
    assert answers[0]["actor"] == "operator"
    assert answers[0]["text"] == ANSWER


def test_the_second_attempt_reached_done_and_the_story_was_verified(
    answered: dict[str, Any],
) -> None:
    detail = answered["detail"]
    build = next(step for step in detail["steps"] if step["path"] == BUILD)

    assert build["status"] == "done"
    assert build["attempts"] == ATTEMPTS_AFTER_THE_ANSWER
    assert step_status(detail, "stories[0].verify") == "done"


# ── what is on the branch ───────────────────────────────────────────────────────────────


def test_the_question_is_archived_with_the_answer_under_it(
    answered: dict[str, Any], gates: GatesFixture
) -> None:
    """FR-18's archive, on the branch: the blocked file, moved and appended to."""
    worktree = answered["detail"]["run"]["worktree_path"]
    archived = gates.show(worktree, "HEAD", ARCHIVED)

    assert f"Blocking condition: {CONDITION}" in archived
    assert "## Human Answer" in archived
    assert archived.rstrip().endswith(ANSWER)
    assert "· operator" in archived


def test_no_story_file_survived_the_archive_under_its_original_name(
    answered: dict[str, Any], gates: GatesFixture
) -> None:
    """The mechanism the re-plan depends on: the glob was empty at the second dispatch, so
    the file on the branch now is the one the *second* attempt wrote."""
    worktree = answered["detail"]["run"]["worktree_path"]

    rewritten = gates.show(worktree, "HEAD", STORY_FILE)

    assert "status: done" in rewritten
    assert "status: blocked" not in rewritten


def test_the_re_dispatch_carried_the_answer_clause_to_the_harness(
    answered: dict[str, Any], gates: GatesFixture
) -> None:
    """The scenario echoes its prompt into the Story file, so the branch holds what was asked."""
    worktree = answered["detail"]["run"]["worktree_path"]

    rewritten = gates.show(worktree, "HEAD", STORY_FILE)

    assert ANSWER_CLAUSE in rewritten


def test_the_work_the_answer_unblocked_is_on_the_branch(
    answered: dict[str, Any], gates: GatesFixture
) -> None:
    worktree = answered["detail"]["run"]["worktree_path"]
    tree = gates.tree(worktree, "HEAD")

    assert WORK_FILE in tree
    assert ARCHIVED in tree
    assert STORY_FILE in tree
