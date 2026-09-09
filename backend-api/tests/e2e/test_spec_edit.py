"""`GET`/`PUT /runs/{id}/files` (story 6-3, SPEC CAP-2, FR-19, FR-23) against the real
engine and real git: the tree branch over a real worktree, and a real Operator commit landed
on a real branch while the Run is parked.

`write_run_file`'s rules are `test_run_files_write.py`'s own coverage over the fakes; what
only the running stack settles is the brief's own AC1 — a `PUT` really writes the worktree
file, really commits `spec: operator edit (orchestrator)` onto the branch, and the gate
record and the tree's own mtime really reflect it — and AC2, that a list file is refused
without ever reaching `Workspace.write`.
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
from tests.e2e.test_answer_signal import wait_for_park
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_project

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_CONFLICT = 409
TIMEOUT_SECONDS = 10.0

SPEC_FOLDER = "specs/gates"
SPEC_FILE = f"{SPEC_FOLDER}/SPEC.md"
STORIES_FILE = f"{SPEC_FOLDER}/stories.yaml"
QUALITY_GATE = "sh check.sh"
DECLARED_BRANCH = "epics/gates"

NEW_SPEC_TEXT = "# Gates spec\n\nedited by the operator while the Run was parked.\n"


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
    """A Run on the gates fixture, walked until it parks `blocked` on story 1 — `needs_you`,
    no terminal session, exactly the shape `write_run_file` requires."""
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

    template_name = f"e2e-gates-spec-edit-{uuid4().hex}"
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


# ── the tree ──────────────────────────────────────────────────────────────────────────────


def test_the_tree_lists_the_spec_folders_own_files(
    parked: dict[str, Any], api: httpx.Client
) -> None:
    response = api.get(f"{RUNS}/{parked['id']}/files")

    assert response.status_code == HTTP_OK
    body = response.json()
    assert body["root"] == SPEC_FOLDER
    paths = {entry["path"] for entry in body["entries"]}
    assert SPEC_FILE in paths
    assert STORIES_FILE in paths


# ── the write ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def edited(api: httpx.Client, parked: dict[str, Any]) -> dict[str, Any]:
    """The `PUT`, made once and shared: every assertion below reads a different fact off
    the one commit it made, rather than writing the file over and over."""
    response = api.put(
        f"{RUNS}/{parked['id']}/files", json={"path": SPEC_FILE, "content": NEW_SPEC_TEXT}
    )
    assert response.status_code == HTTP_OK, response.text
    return {"response": response.json()}


def test_the_response_carries_the_new_entry_and_mtime(edited: dict[str, Any]) -> None:
    body = edited["response"]

    assert body["path"] == SPEC_FILE
    assert body["kind"] == "file"
    assert body["size"] == len(NEW_SPEC_TEXT)
    assert body["mtime"] > 0


def test_the_worktree_file_holds_the_new_text(
    edited: dict[str, Any], parked: dict[str, Any], gates: GatesFixture
) -> None:
    worktree = parked["detail"]["run"]["worktree_path"]

    committed = gates.show(worktree, "HEAD", SPEC_FILE)

    assert committed == NEW_SPEC_TEXT


def test_the_commit_landed_as_the_operators_own_message(
    edited: dict[str, Any], parked: dict[str, Any], api: httpx.Client
) -> None:
    """No new git plumbing is exposed to prove the commit message directly, so this reads
    it back the way the Operator does: the gate record `write_run_file` appends in the same
    unit of work as the commit."""
    detail = api.get(f"{RUNS}/{parked['id']}/detail")
    assert detail.status_code == HTTP_OK, detail.text
    records = [record for record in detail.json()["gate_record"] if record["event"] == "spec_edit"]

    assert len(records) == 1
    assert records[0]["actor"] == "operator"
    assert records[0]["text"] == f"edited {SPEC_FILE}"


def test_the_tree_reflects_the_new_mtime(
    edited: dict[str, Any], parked: dict[str, Any], api: httpx.Client
) -> None:
    """AC5's own words: "the tree's mtime updates" — read here off `GET` with no `path`."""
    response = api.get(f"{RUNS}/{parked['id']}/files")

    row = next(entry for entry in response.json()["entries"] if entry["path"] == SPEC_FILE)
    assert row["mtime"] == edited["response"]["mtime"]
    assert row["size"] == len(NEW_SPEC_TEXT)


# ── the list-file refusal ────────────────────────────────────────────────────────────────


def test_writing_stories_yaml_is_refused_and_nothing_is_written(
    parked: dict[str, Any], api: httpx.Client, gates: GatesFixture
) -> None:
    worktree = parked["detail"]["run"]["worktree_path"]
    before = gates.show(worktree, "HEAD", STORIES_FILE)

    response = api.put(
        f"{RUNS}/{parked['id']}/files", json={"path": STORIES_FILE, "content": "stories: []\n"}
    )

    assert response.status_code == HTTP_CONFLICT, response.text
    assert "planned at" in response.json()["detail"]
    assert "start a new run to change the list" in response.json()["detail"]
    assert gates.show(worktree, "HEAD", STORIES_FILE) == before
