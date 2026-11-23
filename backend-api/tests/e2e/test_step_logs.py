"""Step logs and step identity, read off a real hub-Run (initiative orchestrator-initiative-steps,
epic 1, AD-40).

The unit suite proves each use case on fakes. Only the running stack proves that one Run, walked
by the real engine against real git, reaches the wire in one consistent shape: a deterministic
row's log is on disk and readable through the endpoint, the graph node, the steps-table row and
the drawer name the same `(seq, n)`, the run order is the plan's, and the files-by-epic read
finds the hub's own spec files.

The Run is the hub fixture of `test_hub_run.py`, walked to alpha-epic's done checkpoint and
cancelled at the end. Row paths are those of the suite's own `tests/e2e/templates/hub*.yaml`,
never of a shipped template (hard rule 6).
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.helpers.hub_fixture import HubFixture
from tests.e2e.test_answer_signal import poll_until, step_status
from tests.e2e.test_hub_run import (
    ALPHA_AFTER,
    ALPHA_BASELINE,
    ALPHA_BRANCH,
    ALPHA_SETUP,
    ALPHA_SPEC_FOLDER,
    ALPHA_STORY_BUILD,
    ALPHA_STORY_COMMIT_GUARD,
    BETA_SPEC_FOLDER,
    SUBMODULES,
    start_hub_run,
)
from tests.e2e.test_run_creation import RUNS

HTTP_OK = 200
HTTP_NOT_FOUND = 404
HTTP_UNAUTHORIZED = 401
TIMEOUT_SECONDS = 10.0
PROBLEM_JSON = "application/problem+json"

ALPHA_STORY_FRAME = "epics[0].stories[0]"
ALPHA_EPIC_FRAME = "epics[0]"
ALPHA_STORY_SYNC = "epics[0].stories[0].sync"
ALPHA_SPEC_GATE = "epics[0].spec-gate"
ROOT_FRAME = "root"
CHECKOUT = "checkout"

#: `hub-story.yaml`'s `commit-guard` message for alpha-epic's Story 1.
STORY_1_SUBJECT = "story 1: Ship the alpha feature (orchestrator)"
SHA = re.compile(r"^[0-9a-f]{7,40}$")


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture(scope="module")
def hub(settings: Settings) -> HubFixture:
    version = os.environ.get("BMAD_VERSION")
    if not version:
        pytest.fail(
            "BMAD_VERSION is not set: the hub fixture's `_bmad/` manifest has to state the "
            "version this instance pins (`make e2e` exports it from .env.e2e)"
        )
    return HubFixture(settings.work_dir, version)


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
def parked(api: httpx.Client, hub: HubFixture, test_mode: None) -> Iterator[dict[str, Any]]:
    """A hub-Run walked to alpha-epic's done checkpoint: every alpha row before it has run."""
    run_id, _ = start_hub_run(api, hub)
    try:
        detail = poll_until(
            api,
            run_id,
            lambda detail: (
                detail["run"]["status"] == "needs_you"
                and step_status(detail, ALPHA_AFTER) == "checkpoint"
            ),
            "the Run parking at alpha-epic's own done checkpoint",
        )
        graph = api.get(f"{RUNS}/{run_id}/graph")
        assert graph.status_code == HTTP_OK, graph.text
        yield {"id": run_id, "detail": detail, "graph": graph.json()}
    finally:
        api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def row_of(detail: dict[str, Any], path: str) -> dict[str, Any]:
    return next(step for step in detail["steps"] if step["path"] == path)


def node_of(graph: dict[str, Any], path: str) -> dict[str, Any]:
    return next(node for node in graph["nodes"] if node["id"] == path)


def frame_of(graph: dict[str, Any], frame: str) -> dict[str, Any] | None:
    return next((f for f in graph["run_order"] if f["frame"] == frame), None)


def drawer(api: httpx.Client, run_id: str, seq: int, n: int = 0) -> httpx.Response:
    return api.get(f"{RUNS}/{run_id}/steps/{seq}/attempts/{n}/drawer")


def drawer_of(api: httpx.Client, parked: dict[str, Any], path: str) -> dict[str, Any]:
    seq = node_of(parked["graph"], path)["seq"]
    response = drawer(api, parked["id"], seq)
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


def log_page(api: httpx.Client, run_id: str, attempt_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/attempts/{attempt_id}/log")
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


# ── CAP-4: one key joins node, row and drawer; the run order comes from the plan ─────────────


def test_every_ran_node_carries_its_seq_and_its_latest_attempt(parked: dict[str, Any]) -> None:
    graph, detail = parked["graph"], parked["detail"]
    for path in (CHECKOUT, SUBMODULES, ALPHA_BRANCH, ALPHA_STORY_BUILD, ALPHA_STORY_COMMIT_GUARD):
        node, row = node_of(graph, path), row_of(detail, path)
        assert isinstance(node["seq"], int), path
        assert node["attempt_ns"], path
        assert node["attempt_ns"] == sorted(node["attempt_ns"]), path
        assert node["attempt_n"] == max(node["attempt_ns"]), path
        assert row["attempt_ns"] == node["attempt_ns"], path


def test_a_planned_row_carries_no_attempt(parked: dict[str, Any]) -> None:
    beta_build = node_of(parked["graph"], "epics[1].stories[0].build")
    assert isinstance(beta_build["seq"], int)
    assert beta_build["attempt_n"] is None
    assert beta_build["attempt_ns"] == []


def test_the_story_frame_reads_before_agent_after(parked: dict[str, Any]) -> None:
    frame = frame_of(parked["graph"], ALPHA_STORY_FRAME)
    assert frame is not None
    seqs = [row["seq"] for row in frame["rows"]]
    phases = {row["path"]: row["phase"] for row in frame["rows"]}

    assert seqs == sorted(seqs)
    assert phases[ALPHA_STORY_SYNC] == "BEFORE"
    assert phases[ALPHA_STORY_BUILD] == "AGENT"
    assert phases[ALPHA_STORY_COMMIT_GUARD] == "AFTER"
    assert all(path.startswith(f"{ALPHA_STORY_FRAME}.") for path in phases)


def test_the_epic_frame_holds_only_its_own_rows(parked: dict[str, Any]) -> None:
    frame = frame_of(parked["graph"], ALPHA_EPIC_FRAME)
    assert frame is not None
    phases = {row["path"]: row["phase"] for row in frame["rows"]}

    assert phases[ALPHA_BRANCH] == "BEFORE"
    assert phases[ALPHA_BASELINE] == "BEFORE"
    assert phases[ALPHA_SPEC_GATE] == "AGENT"
    assert phases[ALPHA_AFTER] == "AFTER"
    assert not any(".stories[" in path for path in phases)


def test_the_root_frame_reads_before_its_first_nested_agent(parked: dict[str, Any]) -> None:
    frame = frame_of(parked["graph"], ROOT_FRAME)
    assert frame is not None
    phases = {row["path"]: row["phase"] for row in frame["rows"]}
    assert phases[CHECKOUT] == "BEFORE"
    assert phases[SUBMODULES] == "BEFORE"


# ── CAP-5: the drawer read ────────────────────────────────────────────────────────────────────


def test_the_drawer_of_n_zero_is_the_rows_latest_attempt(
    api: httpx.Client, parked: dict[str, Any]
) -> None:
    node = node_of(parked["graph"], ALPHA_STORY_BUILD)
    body = drawer_of(api, parked, ALPHA_STORY_BUILD)

    assert body["header"]["seq"] == node["seq"]
    assert body["header"]["path"] == ALPHA_STORY_BUILD
    assert body["header"]["kind"] == "agent"
    assert body["header"]["n"] == node["attempt_n"]
    assert [a["n"] for a in body["attempts"]] == node["attempt_ns"]
    assert body["run_order"]["frame"] == ALPHA_STORY_FRAME


def test_a_named_attempt_is_read_by_its_n(api: httpx.Client, parked: dict[str, Any]) -> None:
    node = node_of(parked["graph"], ALPHA_STORY_BUILD)
    response = drawer(api, parked["id"], node["seq"], node["attempt_ns"][0])
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["header"]["n"] == node["attempt_ns"][0]


def test_an_agent_on_the_fake_harness_reads_files_read_not_recorded(
    api: httpx.Client, parked: dict[str, Any]
) -> None:
    """The `fake` extractor declares no files read (B6), so no read path is listed."""
    body = drawer_of(api, parked, ALPHA_STORY_BUILD)
    assert body["files_read"] == {"state": "not_recorded", "paths": []}


def test_a_workdir_commit_reads_its_sha_subject_and_member_paths(
    api: httpx.Client, parked: dict[str, Any]
) -> None:
    body = drawer_of(api, parked, ALPHA_STORY_COMMIT_GUARD)
    written = body["files_written"]

    assert body["files_read"]["state"] == "not_recorded"
    assert written["state"] == "commit"
    assert SHA.match(written["commit"]["sha"])
    assert written["commit"]["message"] == STORY_1_SUBJECT
    assert "repos/alpha/src/alpha_feature.py" in [f["path"] for f in written["files"]]


def test_a_skipped_row_reads_not_run_with_its_reason(
    api: httpx.Client, parked: dict[str, Any]
) -> None:
    row = row_of(parked["detail"], ALPHA_SETUP)
    body = drawer_of(api, parked, ALPHA_SETUP)

    assert row["status"] == "skipped"
    assert body["header"]["n"] is None
    assert body["attempts"] == []
    assert body["log"]["state"] == "not_run"
    assert body["log"]["attempt_id"] is None
    assert body["log"]["reason"] == row["reason"]
    assert body["files_read"]["state"] == "none"
    assert body["files_written"]["state"] == "none"


@pytest.mark.parametrize("target", ["run", "seq", "attempt"])
def test_an_unknown_run_seq_or_attempt_is_a_404_problem(
    api: httpx.Client, parked: dict[str, Any], target: str
) -> None:
    node = node_of(parked["graph"], ALPHA_STORY_BUILD)
    run_id, seq, n = parked["id"], node["seq"], node["attempt_n"]
    if target == "run":
        run_id = str(uuid4())
    elif target == "seq":
        seq = 100_000
    else:
        n = node["attempt_n"] + 50

    response = drawer(api, run_id, seq, n)
    assert response.status_code == HTTP_NOT_FOUND, response.text
    assert response.headers["content-type"].startswith(PROBLEM_JSON)


def test_the_drawer_needs_the_bearer(client: httpx.Client, parked: dict[str, Any]) -> None:
    response = client.get(f"{RUNS}/{parked['id']}/steps/0/attempts/0/drawer")
    assert response.status_code == HTTP_UNAUTHORIZED


# ── CAP-1/2/3: deterministic rows write a log, and the endpoint names its state ──────────────


@pytest.mark.parametrize("path", [SUBMODULES, ALPHA_STORY_SYNC, ALPHA_STORY_COMMIT_GUARD])
def test_a_deterministic_row_has_a_readable_log_of_its_git_operations(
    api: httpx.Client, parked: dict[str, Any], path: str
) -> None:
    body = drawer_of(api, parked, path)
    assert body["log"]["state"] == "text", body["log"]
    assert body["log"]["attempt_id"]

    page = log_page(api, parked["id"], body["log"]["attempt_id"])
    assert page["state"] == "text"
    assert page["eof"] is True
    assert page["lines"], path
    assert page["lines"][0].startswith("> "), page["lines"]


def test_the_commit_log_names_the_commit_operation(
    api: httpx.Client, parked: dict[str, Any]
) -> None:
    body = drawer_of(api, parked, ALPHA_STORY_COMMIT_GUARD)
    page = log_page(api, parked["id"], body["log"]["attempt_id"])
    assert any(line.startswith("> commit ") for line in page["lines"]), page["lines"]


def test_no_log_line_carries_the_orchestrator_token(
    api: httpx.Client, parked: dict[str, Any], token: str
) -> None:
    for path in (CHECKOUT, SUBMODULES, ALPHA_BRANCH, ALPHA_STORY_SYNC, ALPHA_STORY_COMMIT_GUARD):
        attempt_id = drawer_of(api, parked, path)["log"]["attempt_id"]
        page = log_page(api, parked["id"], attempt_id)
        assert not any(token in line for line in page["lines"]), path


# ── CAP-7: files per epic and per story ───────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def by_epic(api: httpx.Client, parked: dict[str, Any]) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{parked['id']}/files-by-epic")
    assert response.status_code == HTTP_OK, response.text
    body: dict[str, Any] = response.json()
    return body


def test_files_by_epic_lists_both_epics_in_plan_order(by_epic: dict[str, Any]) -> None:
    epics = by_epic["epics"]
    assert [e["index"] for e in epics] == [0, 1]
    assert [e["folder"] for e in epics] == [ALPHA_SPEC_FOLDER, BETA_SPEC_FOLDER]
    assert [e["title"] for e in epics] == ["Alpha epic", "Beta epic"]


def test_the_ran_epic_lists_its_present_spec_files_in_order(by_epic: dict[str, Any]) -> None:
    alpha = by_epic["epics"][0]
    assert alpha["files"] == [
        f"{ALPHA_SPEC_FOLDER}/SPEC.md",
        f"{ALPHA_SPEC_FOLDER}/stories.yaml",
        f"{ALPHA_SPEC_FOLDER}/spec-gate-result.md",
    ]


def test_the_epic_not_yet_run_lists_only_the_files_it_was_seeded_with(
    by_epic: dict[str, Any],
) -> None:
    beta = by_epic["epics"][1]
    assert beta["files"] == [f"{BETA_SPEC_FOLDER}/SPEC.md", f"{BETA_SPEC_FOLDER}/stories.yaml"]


def test_a_started_story_carries_its_story_file(by_epic: dict[str, Any]) -> None:
    story = by_epic["epics"][0]["stories"][0]
    assert story["id"] == "1"
    assert story["started"] is True
    assert story["story_file"] == f"{ALPHA_SPEC_FOLDER}/stories/1-work.md"


def test_a_story_not_started_carries_no_file_and_no_change(by_epic: dict[str, Any]) -> None:
    story = by_epic["epics"][1]["stories"][0]
    assert story["started"] is False
    assert story["story_file"] is None
    assert story["changed"] == []


def test_each_changed_path_has_a_diff_and_an_unchanged_one_is_a_404(
    api: httpx.Client, parked: dict[str, Any], by_epic: dict[str, Any]
) -> None:
    story = by_epic["epics"][0]["stories"][0]
    url = f"{RUNS}/{parked['id']}/files-by-epic/diff"
    for path in story["changed"]:
        response = api.get(url, params={"epic": 0, "story": "1", "path": path})
        assert response.status_code == HTTP_OK, response.text
        body = response.json()
        assert body["path"] == path
        assert SHA.match(body["from_sha"]) and SHA.match(body["to_sha"])

    missing = api.get(url, params={"epic": 0, "story": "1", "path": "no/such/file.txt"})
    assert missing.status_code == HTTP_NOT_FOUND, missing.text
    assert missing.headers["content-type"].startswith(PROBLEM_JSON)


def test_an_epic_index_outside_the_list_is_a_404(api: httpx.Client, parked: dict[str, Any]) -> None:
    response = api.get(
        f"{RUNS}/{parked['id']}/files-by-epic/diff",
        params={"epic": 9, "story": "1", "path": "src/alpha_feature.py"},
    )
    assert response.status_code == HTTP_NOT_FOUND, response.text


def test_files_by_epic_of_an_unknown_run_is_a_404(api: httpx.Client) -> None:
    response = api.get(f"{RUNS}/{uuid4()}/files-by-epic")
    assert response.status_code == HTTP_NOT_FOUND, response.text
