"""UJ-3's second and third gates, end to end on the scripted harness (story 6-2, SPEC
CAP-2): a spec checkpoint on story 2's own `agent` row, Continue re-dispatching without a
re-plan, a done checkpoint on story 3's own loop-owned `checkpoint` row after it finishes,
and Continue there resuming the Run all the way to `done`.

Stories 2 and 3 of the gates fixture exist for exactly this story — 6.1's own "Notes for
the next story" names them, `spec_checkpoint: true` and `done_checkpoint: true`. Reaching
them means walking past story 1's own block first (this suite's own Run, not 6.1's
module-scoped one — a second Run is exactly what a fresh gates-fixture clone is for).
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
from tests.e2e.test_answer_signal import poll_until, step_status
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201

SPEC_FOLDER = "specs/gates"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates"
TIMEOUT_SECONDS = 10.0

STORY_1_BUILD = "stories[0].build"
STORY_2_BUILD = "stories[1].build"
STORY_2_COMMIT_GUARD = "stories[1].commit-guard"
STORY_3_COMMIT_GUARD = "stories[2].commit-guard"
STORY_3_CHECKPOINT = "stories[2].after"

STORY_3_TITLE = "Record the shipment"
ANSWER = "unblock story 1 so this suite can reach story 2's own checkpoint"

#: Story 3's own row never resumes, so its Attempt count stays 1 all the way to its own
#: done checkpoint.
CHECKPOINT_ATTEMPTS = 1
#: Story 2's own `build` row: attempt 1 parked at the spec checkpoint, attempt 2 is the
#: Continue's redispatch that implements it.
ATTEMPTS_AFTER_CONTINUE = 2


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
def spec_checkpoint(
    api: httpx.Client, gates: GatesFixture, test_mode: None
) -> Iterator[dict[str, Any]]:
    """A Run walked past story 1's own block (Answer) to story 2's spec checkpoint."""
    project_id = create_project(api)
    created = api.post(
        f"{PROJECTS}/{project_id}/repositories",
        json={
            "url": gates.make(),
            "default_branch": "main",
            "quality_gate_command": QUALITY_GATE,
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    repository_id = str(created.json()["id"])
    clone_check(api, repository_id)

    template_name = f"e2e-gates-checkpoint-{uuid4().hex}"
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
        poll_until(
            api,
            run_id,
            lambda detail: (
                detail["run"]["status"] == "needs_you"
                and step_status(detail, STORY_1_BUILD) == "blocked"
            ),
            "the Run parking blocked on story 1",
        )
        answered = api.post(
            f"{RUNS}/{run_id}/signals", json={"kind": "answer", "payload": {"text": ANSWER}}
        )
        assert answered.status_code == HTTP_OK, answered.text
        detail = poll_until(
            api,
            run_id,
            lambda detail: step_status(detail, STORY_2_BUILD) == "checkpoint",
            "the Run parking at story 2's spec checkpoint",
        )
        yield {"id": run_id, "detail": detail}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel"})


def test_the_spec_checkpoint_parks_on_the_agent_row_itself(
    spec_checkpoint: dict[str, Any],
) -> None:
    detail = spec_checkpoint["detail"]

    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "checkpoint"
    assert detail["alert"]["row_kind"] == "agent"
    assert detail["alert"]["checkpoint_story"] is None


def test_the_spec_checkpoint_admits_continue_and_answer(spec_checkpoint: dict[str, Any]) -> None:
    admitted = spec_checkpoint["detail"]["admitted_signals"]

    assert "continue" in admitted
    assert "answer" in admitted


@pytest.fixture(scope="module")
def done_checkpoint(api: httpx.Client, spec_checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Continue on story 2's spec checkpoint, walked on to story 3's done checkpoint."""
    run_id = spec_checkpoint["id"]
    response = api.post(f"{RUNS}/{run_id}/signals", json={"kind": "continue"})
    assert response.status_code == HTTP_OK, response.text
    detail = poll_until(
        api,
        run_id,
        lambda detail: step_status(detail, STORY_3_CHECKPOINT) == "checkpoint",
        "the Run parking at story 3's done checkpoint",
    )
    return {"id": run_id, "detail": detail}


def test_continue_redispatches_story_2_without_a_new_archive(
    done_checkpoint: dict[str, Any],
) -> None:
    """The AC's own proof: attempt 2 dispatched, the story finished (`commit-guard` done) —
    a Reject archives, a Continue never does, so nothing new lands under `.answers/`."""
    detail = done_checkpoint["detail"]
    build = next(step for step in detail["steps"] if step["path"] == STORY_2_BUILD)

    assert build["attempts"] == ATTEMPTS_AFTER_CONTINUE
    assert step_status(detail, STORY_2_COMMIT_GUARD) == "done"


def test_the_gate_record_holds_continue_for_the_spec_checkpoint(
    done_checkpoint: dict[str, Any],
) -> None:
    records = done_checkpoint["detail"]["gate_record"]
    continues = [
        entry
        for entry in records
        if entry["event"] == "continue" and entry["path"] == STORY_2_BUILD
    ]

    assert len(continues) == 1
    assert continues[0]["actor"] == "operator"


def test_the_done_checkpoint_parks_on_the_loops_own_row(done_checkpoint: dict[str, Any]) -> None:
    alert = done_checkpoint["detail"]["alert"]

    assert alert["park_kind"] == "checkpoint"
    assert alert["row_kind"] == "checkpoint"


def test_the_done_checkpoint_summarises_story_3(done_checkpoint: dict[str, Any]) -> None:
    story = done_checkpoint["detail"]["alert"]["checkpoint_story"]

    assert story is not None
    assert story["story_id"] == "3"
    assert story["title"] == STORY_3_TITLE
    assert story["attempts"] == CHECKPOINT_ATTEMPTS
    assert story["verify"] == "done"


def test_the_done_checkpoint_admits_continue_but_not_answer(
    done_checkpoint: dict[str, Any],
) -> None:
    admitted = done_checkpoint["detail"]["admitted_signals"]

    assert "continue" in admitted
    assert "answer" not in admitted


def test_continue_on_the_done_checkpoint_resumes_the_run_to_done(
    api: httpx.Client, done_checkpoint: dict[str, Any], gates: GatesFixture
) -> None:
    run_id = done_checkpoint["id"]

    response = api.post(f"{RUNS}/{run_id}/signals", json={"kind": "continue"})
    assert response.status_code == HTTP_OK, response.text
    detail = poll_until(
        api, run_id, lambda detail: detail["run"]["status"] == "done", "the Run finishing"
    )

    assert step_status(detail, STORY_3_COMMIT_GUARD) == "done"
    assert step_status(detail, "push") == "done"
    # `pr.link` (`application/steps/pr_link.py`) never appends a compare URL for the
    # fixture's own `file://` origin — "no compare link for this host" is `done` too, by
    # design — so the Run finishing with no `compare_urls` is the correct outcome here, not
    # a failure to push.
    assert detail["run"]["compare_urls"] == []

    worktree = detail["run"]["worktree_path"]
    tree = gates.tree(worktree, "HEAD")
    assert "NOTIFY.md" in tree
    assert "PLAN.md" in tree
    assert "SHIP.md" in tree
