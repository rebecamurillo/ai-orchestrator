"""Template type, engine lane, frozen versions and `git.branch_delete` against the running
stack (initiative orchestrator-initiative-steps, epic 3, SPEC CAP-1..CAP-4).

The unit suite proves each rule over fakes. What only the running stack settles: the stored
version round-trips `type` through real HTTP and Postgres; `GET /queue` reads `lane` off the
real DBOS queues; `POST /runs` and pre-flight refuse a version that is not stored; and a
`git.branch_delete` row walked by the real engine deletes a branch on a real bare remote and
logs it.

Every template here is a fresh name the module owns (hard rule 6: no shipped template is read).
Every Run this module starts is cancelled when its test ends, unless it already ended.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import (
    DOCKER_TIMEOUT_SECONDS,
    REPO_ROOT,
    Fixtures,
    manifest_stating,
)
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
HTTP_UNPROCESSABLE = 422
QUEUE = "/api/v1/queue"
TIMEOUT_SECONDS = 10.0
RUN_TIMEOUT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 0.5
MISSING_VERSION = 9
VERSION_2 = 2
#: `CHECKPOINT`'s `type:` line: after `name`, `version` and `description`.
TYPE_LINE = 4
INVALID_VALUE_CODE = "template-invalid-value"
LANES = {"walk", "interactive"}
TERMINAL = {"done", "failed", "cancelled"}

BASE_INPUTS = (
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
)

#: `{type_line}` is either empty or one `type: …` line; the text after it is the same.
CHECKPOINT = (
    "name: {name}\nversion: {version}\ndescription: e2e epic 3 fixture\n"
    "{type_line}" + BASE_INPUTS + "steps:\n"
    "  - id: pause\n"
    "    uses: checkpoint\n"
    "    gate: human\n"
)

#: Version 1 has two rows, version 2 one: which version was planned shows in the rows.
FROZEN_V1 = (
    "name: {name}\nversion: 1\ndescription: e2e frozen v1\n" + BASE_INPUTS + "steps:\n"
    "  - id: touch\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
    "  - id: link\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)
FROZEN_V2 = (
    "name: {name}\nversion: 2\ndescription: e2e frozen v2\n" + BASE_INPUTS + "steps:\n"
    "  - id: touch\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
)

BRANCH_DELETE = (
    "name: {name}\nversion: 1\ndescription: e2e branch delete\n" + BASE_INPUTS + "steps:\n"
    "  - id: checkout\n"
    "    uses: git.worktree\n"
    "    with: {{ base: '{{{{base_branch}}}}', branch: '{work_branch}' }}\n"
    "    gate: deterministic\n"
    "  - id: delete\n"
    "    uses: git.branch_delete\n"
    "    with: {{ branch: '{branch}' }}\n"
    "    gate: deterministic\n"
)

#: `$1` the bare repository; `$2` an action; `$3` the branch. Prints `present` or `absent`
#: for `has`. Fails when the repository is not on this side, so the other route is tried.
REMOTE_BRANCH = """
set -e
repo="$1"; action="$2"; branch="$3"
test -d "$repo"
case "$action" in
  add) git --git-dir="$repo" branch "$branch" main ;;
  has)
    if git --git-dir="$repo" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null
    then echo present; else echo absent; fi ;;
esac
"""


def remote(fixtures: Fixtures, url: str, action: str, branch: str) -> str:
    """Run `REMOTE_BRANCH` where the bare repository is: here, else in the container."""
    repo = url.removeprefix("file://")
    script = ["sh", "-c", REMOTE_BRANCH, "sh", repo, action, branch]
    refusals: list[str] = []
    for command in (
        script,
        ["docker", "compose", "exec", "-T", "backend-api", *script],
    ):
        try:
            completed = subprocess.run(  # fixed argv, no shell
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
                timeout=DOCKER_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            refusals.append(str(error))
            continue
        if completed.returncode == 0:
            return completed.stdout.strip()
        refusals.append((completed.stderr or completed.stdout).strip())
    pytest.fail(f"cannot reach {repo} to {action} {branch}: " + " | ".join(refusals))


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def fixtures(settings: Settings) -> Fixtures:
    return Fixtures(settings.work_dir)


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


def fresh_repository(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> tuple[str, str]:
    """A clone-checked Repository on its own bare remote: `(repository_id, url)`."""
    url = fixtures.make(manifest_stating(settings.bmad_version))
    repository_id = create_repository(api, create_project(api), url)
    clone_check(api, repository_id)
    return repository_id, url


@pytest.fixture(scope="module")
def repository_id(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> str:
    return fresh_repository(api, fixtures, settings)[0]


def save(api: httpx.Client, name: str, text: str) -> httpx.Response:
    return api.post(f"{TEMPLATES}/{name}/versions", json={"yaml": text})


def saved(api: httpx.Client, name: str, text: str) -> dict[str, Any]:
    response = save(api, name, text)
    assert response.status_code == HTTP_CREATED, response.text
    body: dict[str, Any] = response.json()
    return body


def checkpoint_text(name: str, type_line: str = "", version: int = 1) -> str:
    return CHECKPOINT.format(name=name, version=version, type_line=type_line)


def start(api: httpx.Client, repository_id: str, name: str, version: int = 1) -> str:
    payload = run_payload(
        name,
        repository_id,
        template_version=version,
        project_id=project_id_of(api, repository_id),
    )
    response = api.post(RUNS, json=payload)
    assert response.status_code == HTTP_CREATED, response.text
    return str(response.json()["run"]["id"])


def detail_of(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def wait_until(api: httpx.Client, run_id: str, statuses: set[str]) -> dict[str, Any]:
    deadline = time.monotonic() + RUN_TIMEOUT_SECONDS
    detail = detail_of(api, run_id)
    while detail["run"]["status"] not in statuses and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        detail = detail_of(api, run_id)
    if detail["run"]["status"] not in statuses:
        alert = detail["alert"] or {}
        pytest.fail(
            f"run {run_id} did not reach {sorted(statuses)} within {RUN_TIMEOUT_SECONDS:.0f}s: "
            f"{detail['run']['status']} at {alert.get('park_kind')}: {alert.get('reason')}; "
            f"rows: {[(step['path'], step['status']) for step in detail['steps']]}"
        )
    return detail


def cancel(api: httpx.Client, run_id: str) -> None:
    """Best effort: a Run that already ended refuses the signal, which is fine here."""
    api.post(f"{RUNS}/{run_id}/signals", json={"kind": "cancel", "payload": {"confirm": True}})


def row(detail: dict[str, Any], path: str) -> dict[str, Any]:
    return next(step for step in detail["steps"] if step["path"] == path)


# ── CAP-1: a template declares its type ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("type_line", "expected"),
    [("type: interactive\n", "interactive"), ("type: auto\n", "auto"), ("", "auto")],
)
def test_a_stored_version_reads_its_type(api: httpx.Client, type_line: str, expected: str) -> None:
    name = f"e2e-type-{uuid4().hex}"

    created = saved(api, name, checkpoint_text(name, type_line))
    response = api.get(f"{TEMPLATES}/{name}/1")

    assert created["type"] == expected
    assert response.status_code == HTTP_OK, response.text
    assert response.json()["type"] == expected


@pytest.mark.parametrize("value", ["manual", "[auto]"])
def test_a_type_outside_the_two_values_is_refused_at_its_line(
    api: httpx.Client, value: str
) -> None:
    """The validator's existing invalid-value error (story 1): it names the `type:` line,
    whose text carries the key and the value."""
    name = f"e2e-type-{uuid4().hex}"
    text = checkpoint_text(name, f"type: {value}\n")

    stored = save(api, name, text)
    validated = api.post(f"{TEMPLATES}/{name}/validate", json={"yaml": text})

    assert text.splitlines()[TYPE_LINE - 1] == f"type: {value}"
    assert stored.status_code == HTTP_UNPROCESSABLE, stored.text
    assert stored.json()["detail"].startswith(f"line {TYPE_LINE}:"), stored.json()
    assert validated.status_code == HTTP_OK, validated.text
    errors = validated.json()["errors"]
    assert [(error["line"], error["code"]) for error in errors] == [
        (TYPE_LINE, INVALID_VALUE_CODE)
    ], errors
    assert [(error["line"], error["code"]) for error in stored.json()["errors"]] == [
        (TYPE_LINE, INVALID_VALUE_CODE)
    ], stored.json()


# ── CAP-2: the lane on the queue ─────────────────────────────────────────────────────────


def test_every_queue_row_names_a_lane_and_positions_count_per_lane(api: httpx.Client) -> None:
    response = api.get(QUEUE)

    assert response.status_code == HTTP_OK, response.text
    items = response.json()["items"]
    for lane in LANES:
        positions = [item["position"] for item in items if item["lane"] == lane]
        numbered = [position for position in positions if position is not None]
        assert numbered == list(range(1, len(numbered) + 1)), (lane, items)
    assert {item["lane"] for item in items} <= LANES, items


def test_an_interactive_template_with_no_conversation_row_walks_in_the_walk_lane(
    api: httpx.Client, repository_id: str
) -> None:
    name = f"e2e-lane-{uuid4().hex}"
    saved(api, name, checkpoint_text(name, "type: interactive\n"))
    run_id = start(api, repository_id, name)
    try:
        wait_until(api, run_id, {"needs_you"})

        response = api.get(QUEUE)

        assert response.status_code == HTTP_OK, response.text
        entry = next(
            (item for item in response.json()["items"] if item["run"]["id"] == run_id), None
        )
        assert entry is not None, response.json()
        assert entry["lane"] == "walk"
    finally:
        cancel(api, run_id)


# ── CAP-3: a Run from a frozen version ───────────────────────────────────────────────────


@pytest.fixture(scope="module")
def frozen(api: httpx.Client) -> str:
    name = f"e2e-frozen-{uuid4().hex}"
    saved(api, name, FROZEN_V1.format(name=name))
    saved(api, name, FROZEN_V2.format(name=name))
    return name


def test_a_run_at_version_1_plans_version_1_while_version_2_is_stored(
    api: httpx.Client, repository_id: str, frozen: str
) -> None:
    run_id = start(api, repository_id, frozen, version=1)
    try:
        detail = detail_of(api, run_id)

        assert detail["run"]["template"] == frozen
        assert detail["run"]["version"] == 1
        paths = [step["path"] for step in detail["steps"]]
        assert "touch" in paths
        assert "link" in paths
    finally:
        cancel(api, run_id)


def test_a_run_at_version_2_plans_version_2(
    api: httpx.Client, repository_id: str, frozen: str
) -> None:
    run_id = start(api, repository_id, frozen, version=VERSION_2)
    try:
        detail = detail_of(api, run_id)

        assert detail["run"]["version"] == VERSION_2
        paths = [step["path"] for step in detail["steps"]]
        assert "touch" in paths
        assert "link" not in paths
    finally:
        cancel(api, run_id)


def test_a_version_that_is_not_stored_is_refused_naming_template_and_version(
    api: httpx.Client, repository_id: str, frozen: str
) -> None:
    project_id = project_id_of(api, repository_id)
    payload = run_payload(
        frozen, repository_id, template_version=MISSING_VERSION, project_id=project_id
    )

    response = api.post(RUNS, json=payload)

    assert response.status_code == HTTP_UNPROCESSABLE, response.text
    errors = response.json()["errors"]
    assert errors[0]["template"] == frozen, errors
    assert errors[0]["version"] == str(MISSING_VERSION), errors
    listed = api.get(RUNS, params={"project_id": project_id})
    assert listed.status_code == HTTP_OK, listed.text
    assert all(
        not (run["template"] == frozen and run["version"] == MISSING_VERSION)
        for run in listed.json()["items"]
    )


def test_preflight_names_the_missing_template_version(
    api: httpx.Client, repository_id: str, frozen: str
) -> None:
    payload = run_payload(
        frozen,
        repository_id,
        template_version=MISSING_VERSION,
        project_id=project_id_of(api, repository_id),
    )

    response = api.post(f"{RUNS}/preflight", json=payload)

    assert response.status_code == HTTP_OK, response.text
    plan_error = response.json()["plan_error"]
    assert plan_error is not None, response.json()
    assert plan_error["template"] == frozen
    assert plan_error["version"] == MISSING_VERSION


# ── CAP-4: the git.branch_delete kind ────────────────────────────────────────────────────


def branch_delete_text(name: str, branch: str) -> str:
    return BRANCH_DELETE.format(name=name, branch=branch, work_branch=f"e2e/del-{uuid4().hex}")


def test_a_branch_delete_step_validates_and_an_unknown_with_key_is_refused(
    api: httpx.Client,
) -> None:
    name = f"e2e-delete-{uuid4().hex}"
    good = branch_delete_text(name, "spec/demo")
    bad = good.replace("{ branch: 'spec/demo' }", "{ branch: 'spec/demo', force: true }")

    accepted = api.post(f"{TEMPLATES}/{name}/validate", json={"yaml": good})
    refused = api.post(f"{TEMPLATES}/{name}/validate", json={"yaml": bad})

    assert accepted.status_code == HTTP_OK, accepted.text
    assert accepted.json()["errors"] == []
    assert refused.status_code == HTTP_OK, refused.text
    assert refused.json()["errors"], refused.json()


def test_the_graph_draws_one_deterministic_branch_delete_node(api: httpx.Client) -> None:
    name = f"e2e-delete-{uuid4().hex}"
    saved(api, name, branch_delete_text(name, "spec/demo"))

    response = api.get(f"{TEMPLATES}/{name}/1/graph")

    assert response.status_code == HTTP_OK, response.text
    nodes = [node for node in response.json()["nodes"] if node["kind"] == "git.branch_delete"]
    assert [node["id"] for node in nodes] == ["delete"]
    assert nodes[0]["gate"] == "deterministic"
    assert nodes[0]["agent"] is False


@pytest.fixture
def delete_run(api: httpx.Client, fixtures: Fixtures, settings: Settings) -> Iterator[Any]:
    """Start a branch-delete Run on a fresh remote; yields `run(branch, seed) -> (id, url)`."""
    started: list[str] = []

    def run(branch: str, *, seed: bool) -> tuple[str, str]:
        repository_id, url = fresh_repository(api, fixtures, settings)
        if seed:
            remote(fixtures, url, "add", branch)
            assert remote(fixtures, url, "has", branch) == "present"
        name = f"e2e-delete-{uuid4().hex}"
        saved(api, name, branch_delete_text(name, branch))
        run_id = start(api, repository_id, name)
        started.append(run_id)
        return run_id, url

    yield run
    for run_id in started:
        cancel(api, run_id)


def log_lines(api: httpx.Client, run_id: str, seq: int) -> list[str]:
    drawer = api.get(f"{RUNS}/{run_id}/steps/{seq}/attempts/0/drawer")
    assert drawer.status_code == HTTP_OK, drawer.text
    log = drawer.json()["log"]
    assert log["state"] == "text", log
    page = api.get(f"{RUNS}/{run_id}/attempts/{log['attempt_id']}/log")
    assert page.status_code == HTTP_OK, page.text
    return list(page.json()["lines"])


def seq_of(api: httpx.Client, run_id: str, path: str) -> int:
    response = api.get(f"{RUNS}/{run_id}/graph")
    assert response.status_code == HTTP_OK, response.text
    return int(next(node for node in response.json()["nodes"] if node["id"] == path)["seq"])


def test_a_branch_the_remote_holds_is_deleted_and_logged(
    api: httpx.Client, fixtures: Fixtures, delete_run: Any
) -> None:
    run_id, url = delete_run("spec/demo", seed=True)

    detail = wait_until(api, run_id, TERMINAL | {"needs_you"})

    assert detail["run"]["status"] == "done", detail["alert"]
    step = row(detail, "delete")
    assert step["status"] == "done"
    assert step["reason"] == "deleted origin/spec/demo"
    assert remote(fixtures, url, "has", "spec/demo") == "absent"
    lines = log_lines(api, run_id, seq_of(api, run_id, "delete"))
    assert any("git push origin --delete spec/demo" in line for line in lines), lines
    assert any(line.strip() == "deleted" for line in lines), lines


def test_a_branch_already_gone_ends_done_with_its_log(api: httpx.Client, delete_run: Any) -> None:
    run_id, _ = delete_run("spec/never-pushed", seed=False)

    detail = wait_until(api, run_id, TERMINAL | {"needs_you"})

    assert detail["run"]["status"] == "done", detail["alert"]
    assert row(detail, "delete")["reason"] == "already gone"
    lines = log_lines(api, run_id, seq_of(api, run_id, "delete"))
    assert any("git push origin --delete spec/never-pushed" in line for line in lines), lines
    assert any(line.strip() == "already gone" for line in lines), lines


def test_the_default_branch_is_refused_and_left_on_the_remote(
    api: httpx.Client, fixtures: Fixtures, delete_run: Any
) -> None:
    run_id, url = delete_run("main", seed=False)

    detail = wait_until(api, run_id, TERMINAL | {"needs_you"})

    assert detail["run"]["status"] == "needs_you"
    assert detail["alert"]["park_kind"] == "misconfigured", detail["alert"]
    assert detail["alert"]["reason"] == "refuses to delete the default branch main"
    assert remote(fixtures, url, "has", "main") == "present"
