"""The initiative record against the running stack (initiative orchestrator-initiative-steps,
epic 7, SPEC CAP-1..CAP-6).

The unit suite proves each rule over the shared fakes. What only the running stack settles:
`POST /initiatives` pushes `spec/{slug}` to a real bare origin through the real git adapter,
stores the initiative and its spec Run in one unit of work in Postgres, and the real engine
walks that Run to its first `conversation` stop on the scripted `fake` harness; the reads
compute the status and the attention from what is stored; the board and the Run detail carry
the initiative tag; `start-next` moves the real walk to the next conversation step and refuses
the gate; cancel ends the Run and deletes the branch on the origin; the partial unique index
holds the slug only while the initiative is open; the package delete is refused while one is.

Every package, template and slug is fresh, every origin a new bare repository this module
writes (hard rule 6: no shipped template and no hub `package/` is read). Every initiative the
module creates is cancelled when its test ends.
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Iterator
from typing import Any
from uuid import uuid4

import httpx
import pytest

from orchestrator.infrastructure.settings import Settings
from tests.e2e.test_clone_check import (
    DOCKER_TIMEOUT_SECONDS,
    FIXTURE_DIRECTORY,
    REPO_ROOT,
    UNKNOWN_ID,
    manifest_stating,
)
from tests.e2e.test_mcp_setup_path import Mcp
from tests.e2e.test_run_creation import PROJECTS, RUNS, clone_check, create_repository

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NO_CONTENT = 204
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
TIMEOUT_SECONDS = 30.0
#: A signal that kills a running turn answers after the runner's SIGTERM grace (10 s).
SIGNAL_TIMEOUT_SECONDS = 60.0
WAIT_SECONDS = 120.0
POLL_INTERVAL_SECONDS = 0.5

INITIATIVES = "/api/v1/initiatives"
PATH = "pkg"
FIRST_MESSAGE = "Start here: the initiative's first message."
QUICK = "exit_code: 0\n"
TERMINAL = {"done", "failed", "cancelled"}

DEFAULTS = {
    "default_budget_usd": "5.00",
    "default_harness": "fake",
    "default_model": None,
    "default_autonomy": None,
    "default_senior_model": None,
}

SPEC = """name: spec
version: 1
description: e2e epic 7 spec workflow
type: interactive
inputs:
  project:           { type: project,    required: true }
  repository:        { type: repository, required: true }
  base_branch:       { type: string,     required: true }
  slug:              { type: string,     required: true }
  branch:            { type: string,     required: true }
  first_turn:        { type: string,     required: false }
  round_steps:       { type: string,     required: false }
  initiative_folder: { type: string,     required: false }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: '{{base_branch}}', branch: '{{branch}}', mode: attach }
    gate: deterministic
@ROWS@  - id: gate
    uses: agent
    role: spec-gate
    with: { skill: spec-gate }
    prompts:
      dispatch: "Run {skill}."
      rendered: "Rendered at {path}."
    expect:
      files: ["docs/gate.md"]
      success: [pass, fail]
      blocked: [blocked]
    gate: liveness
"""

CONVERSATION = """  - id: @STEP@
    uses: conversation
    role: plan
    gate: human
    with: { step: @STEP@, skill: skills/talk/SKILL.md, persona: personas/analyst.md }
    expect:
      files: ["docs/@STEP@.md"]
      success: [done]
      blocked: [blocked]
    writes: ["docs/@STEP@.md"]
    prompts:
      open: "Open @STEP@."
      close: "Close @STEP@ as {attempt_id}."
"""

MERGE = """name: merge
version: 1
description: e2e epic 7 merge workflow
type: interactive
steps:
  - id: merge
    uses: git.merge
    gate: deterministic
"""

#: `$1` directory, `$2` name, `$3` manifest; then pairs of repository path and content.
MAKE_HUB_ORIGIN = """
set -e
dir="$1"; name="$2"; manifest="$3"; shift 3
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare --initial-branch=main "$dir/$name.git"
git init --quiet --initial-branch=main "$dir/$name.seed"
cd "$dir/$name.seed"
git config user.email e2e@example.invalid
git config user.name e2e
echo "$name" > README.md
mkdir -p _bmad/_config
printf '%s' "$manifest" > _bmad/_config/manifest.yaml
while [ "$#" -ge 2 ]; do
  mkdir -p "$(dirname "$1")"
  printf '%s' "$2" > "$1"
  shift 2
done
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""

#: `$1` the origin's `file://` URL, `$2` the branch; prints the branch's sha or nothing.
LS_REMOTE = 'git ls-remote "$1" "refs/heads/$2" | cut -f1'


def hub_files(package: str) -> dict[str, str]:
    rows = "".join(CONVERSATION.replace("@STEP@", step) for step in ("intake", "product"))
    files = {
        f"{PATH}/package.yaml": (
            f"name: {package}\nsequence:\n"
            "  - { workflow: spec, template: templates/spec.yaml }\n"
            "  - { workflow: merge, template: templates/merge.yaml }\n"
            "gate: { pass: [pass], fail: [fail], owners_key: owners }\n"
            "status_map: { final: done, blocked: waiting for her }\n"
        ),
        f"{PATH}/templates/spec.yaml": SPEC.replace("@ROWS@", rows),
        f"{PATH}/templates/merge.yaml": MERGE,
        ".fake-harness/default.yaml": QUICK,
        "personas/analyst.md": "The analyst.\n",
        "skills/talk/SKILL.md": "Talk the step through.\n",
    }
    return files


def in_stack(script: str, *arguments: str) -> str:
    """Run `script` where the backend sees the work volume, the container first; its stdout."""
    refusals: list[str] = []
    for prefix in (("docker", "compose", "exec", "-T", "backend-api"), ()):
        command = [*prefix, "sh", "-c", script, "sh", *arguments]
        try:
            done = subprocess.run(  # fixed argv, no shell
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
        if done.returncode == 0:
            return done.stdout
        refusals.append((done.stderr or done.stdout).strip())
    pytest.fail("no route into the stack's work volume: " + " | ".join(refusals))


def hub_origin(settings: Settings, files: dict[str, str]) -> str:
    directory = settings.work_dir / FIXTURE_DIRECTORY
    name = f"hub-{uuid4()}"
    pairs = [item for pair in files.items() for item in pair]
    in_stack(MAKE_HUB_ORIGIN, str(directory), name, manifest_stating(settings.bmad_version), *pairs)
    return f"file://{directory}/{name}.git"


def branch_sha(url: str, branch: str) -> str:
    return in_stack(LS_REMOTE, url, branch).strip()


def wait_for[T](read: Callable[[], T], done: Callable[[T], bool], what: str) -> T:
    deadline = time.monotonic() + WAIT_SECONDS
    value = read()
    while not done(value) and time.monotonic() < deadline:
        time.sleep(POLL_INTERVAL_SECONDS)
        value = read()
    if not done(value):
        pytest.fail(f"{what} did not happen within {WAIT_SECONDS:.0f}s; last read: {value}")
    return value


@pytest.fixture(scope="module")
def settings(stack: str) -> Settings:
    return Settings()


@pytest.fixture(scope="module")
def api(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client


class Hub:
    """A project with run defaults, a clone-checked hub and its installed fixture package."""

    def __init__(self, api: httpx.Client, settings: Settings) -> None:
        self.api = api
        self.package = f"e2e-init-{uuid4().hex[:12]}"
        created = api.post(PROJECTS, json={"name": f"e2e initiatives {uuid4()}"})
        assert created.status_code == HTTP_CREATED, created.text
        self.project_id = str(created.json()["id"])
        self.project_name = str(created.json()["name"])
        defaults = api.put(f"{PROJECTS}/{self.project_id}/run-defaults", json=DEFAULTS)
        assert defaults.status_code == HTTP_OK, defaults.text
        self.url = hub_origin(settings, hub_files(self.package))
        self.repository_id = create_repository(api, self.project_id, self.url)
        clone_check(api, self.repository_id)
        installed = api.put(
            f"{PROJECTS}/{self.project_id}/package",
            json={"repository_id": self.repository_id, "path": PATH, "ref": "main"},
        )
        assert installed.status_code == HTTP_OK, installed.text
        self.repository_slug = str(
            api.get(f"/api/v1/repositories/{self.repository_id}").json()["slug"]
        )
        self.created: list[str] = []

    def create(self, name: str, first_message: str = FIRST_MESSAGE) -> httpx.Response:
        response = self.api.post(
            INITIATIVES,
            json={"project_id": self.project_id, "name": name, "first_message": first_message},
            timeout=SIGNAL_TIMEOUT_SECONDS,
        )
        if response.status_code == HTTP_CREATED:
            self.created.append(str(response.json()["id"]))
        return response

    def new(self, name: str | None = None) -> dict[str, Any]:
        response = self.create(name or f"Snake {uuid4().hex[:8]}")
        assert response.status_code == HTTP_CREATED, response.text
        return dict(response.json())

    def cleanup(self) -> None:
        for initiative_id in self.created:
            self.api.post(f"{INITIATIVES}/{initiative_id}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)


@pytest.fixture
def hub(api: httpx.Client, settings: Settings) -> Iterator[Hub]:
    made = Hub(api, settings)
    yield made
    made.cleanup()


def detail_of(api: httpx.Client, initiative_id: str, **params: str) -> dict[str, Any]:
    response = api.get(f"{INITIATIVES}/{initiative_id}", params=params)
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def run_detail(api: httpx.Client, run_id: str) -> dict[str, Any]:
    response = api.get(f"{RUNS}/{run_id}/detail")
    assert response.status_code == HTTP_OK, response.text
    return dict(response.json())


def spec_run_id(detail: dict[str, Any]) -> str:
    return str(detail["runs"][0]["id"])


def parked_on(api: httpx.Client, run_id: str, step: str) -> dict[str, Any]:
    """The Run's detail once it waits on the conversation row `step` with no turn running."""

    def parked(detail: dict[str, Any]) -> bool:
        if detail["run"]["status"] in TERMINAL:
            pytest.fail(f"run {run_id} ended {detail['run']['status']}: {detail['alert']}")
        alert = detail["alert"] or {}
        row = next(entry for entry in detail["steps"] if entry["path"] == step)
        return (
            detail["run"]["status"] == "needs_you"
            and alert.get("park_kind") == "conversation"
            and row["status"] == "checkpoint"
            and detail.get("initiative") is not None
        )

    return wait_for(lambda: run_detail(api, run_id), parked, f"run {run_id} parking on {step}")


def your_turn(api: httpx.Client, initiative_id: str) -> dict[str, Any]:
    """The initiative's detail once its spec Run waits for her answer."""
    return wait_for(
        lambda: detail_of(api, initiative_id),
        lambda detail: detail["attention"] == "your_turn",
        f"initiative {initiative_id} reading your_turn",
    )


def step_of(detail: dict[str, Any], step: str) -> dict[str, Any]:
    spec = detail["workflows"][0]
    return next(entry for entry in spec["steps"] if entry["id"] == step)


# ── CAP-3, CAP-5: create ────────────────────────────────────────────────────────────────


def test_create_pushes_the_spec_branch_and_starts_the_spec_run_at_the_frozen_version(
    api: httpx.Client, hub: Hub
) -> None:
    name = f"Snake {uuid4().hex[:8]}"
    slug = name.lower().replace(" ", "-")

    detail = hub.new(name)

    main_sha = branch_sha(hub.url, "main")
    assert branch_sha(hub.url, f"spec/{slug}") == main_sha
    assert (detail["slug"], detail["name"], detail["first_message"]) == (
        slug,
        name,
        FIRST_MESSAGE,
    )
    assert detail["round"] == 1
    assert (detail["project_id"], detail["repository_id"]) == (hub.project_id, hub.repository_id)
    assert detail["project"] == {"id": hub.project_id, "name": hub.project_name}
    assert detail["hub"]["id"] == hub.repository_id
    assert detail["folder"] == f"initiatives/{slug}"
    assert detail["package"] == hub.package
    assert detail["status"] == "running"
    assert detail["cancelled_at"] is None
    assert detail["pr_merged_at"] is None
    assert detail["workflow_count"] == 1
    assert detail["current_position"] == 1
    assert [w["workflow"] for w in detail["workflows"]] == ["spec"]
    spec = detail["workflows"][0]
    assert (spec["template"], spec["version"], spec["type"]) == (
        f"{hub.package}.spec",
        1,
        "interactive",
    )
    assert [s["id"] for s in spec["steps"]] == ["intake", "product", "gate", "merge"]

    [run] = detail["runs"]
    assert (run["template_name"], run["template_version"]) == (f"{hub.package}.spec", 1)
    assert (run["round"], run["position"]) == (1, 0)
    inputs = run_detail(api, run["id"])["run"]["inputs"]
    assert inputs["slug"] == slug
    assert inputs["branch"] == f"spec/{slug}"
    assert inputs["first_turn"] == FIRST_MESSAGE
    assert inputs["initiative_folder"] == "initiatives"


def test_create_refuses_a_held_slug_naming_the_holder_and_frees_it_once_cancelled(
    api: httpx.Client, hub: Hub
) -> None:
    name = f"Snake {uuid4().hex[:8]}"
    holder = hub.new(name)

    refused = hub.create(name)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    assert f"{holder['name']} ({holder['id']})" in refused.json()["detail"]

    cancelled = api.post(f"{INITIATIVES}/{holder['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    assert cancelled.status_code == HTTP_OK, cancelled.text
    assert cancelled.json()["branch_cleanup_error"] is None

    again = hub.create(name)
    assert again.status_code == HTTP_CREATED, again.text
    assert again.json()["id"] != holder["id"]


def test_create_refuses_a_spec_branch_already_on_the_hub_and_touches_no_branch(
    api: httpx.Client, settings: Settings, hub: Hub
) -> None:
    slug = f"taken-{uuid4().hex[:8]}"
    push = (
        'set -e; tmp=$(mktemp -d); git clone --quiet "$1" "$tmp/c"; '
        'git -C "$tmp/c" push --quiet origin "main:refs/heads/spec/$2"; rm -rf "$tmp"'
    )
    in_stack(push, hub.url, slug)
    before = branch_sha(hub.url, f"spec/{slug}")

    refused = hub.create(slug)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    assert refused.json()["detail"] == (
        f"branch spec/{slug} already exists on the hub; delete it or choose another name"
    )
    assert branch_sha(hub.url, f"spec/{slug}") == before
    listed = api.get(INITIATIVES, params={"project_id": hub.project_id, "filter": "all"})
    assert listed.json()["items"] == []


def test_create_refuses_an_unknown_project_no_package_a_blank_name_and_an_unknown_key(
    api: httpx.Client, hub: Hub
) -> None:
    body = {"project_id": hub.project_id, "name": "Snake", "first_message": "hello"}
    bare = api.post(PROJECTS, json={"name": f"e2e no package {uuid4()}"})
    assert bare.status_code == HTTP_CREATED, bare.text

    unknown = api.post(INITIATIVES, json={**body, "project_id": UNKNOWN_ID})
    no_package = api.post(INITIATIVES, json={**body, "project_id": bare.json()["id"]})
    blank = api.post(INITIATIVES, json={**body, "name": "   "})
    extra = api.post(INITIATIVES, json={**body, "colour": "red"})

    assert unknown.status_code == HTTP_NOT_FOUND, unknown.text
    assert no_package.status_code == HTTP_CONFLICT, no_package.text
    assert "no package installed on project" in no_package.json()["detail"]
    assert blank.status_code == HTTP_UNPROCESSABLE, blank.text
    assert extra.status_code == HTTP_UNPROCESSABLE, extra.text
    listed = api.get(INITIATIVES, params={"project_id": hub.project_id, "filter": "all"})
    assert listed.json()["items"] == []


# ── CAP-2, CAP-4, CAP-6: the reads over a walked Run ────────────────────────────────────


def test_a_spec_run_at_its_first_conversation_reads_running_your_turn_everywhere(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    run_id = spec_run_id(created)

    run = parked_on(api, run_id, "intake")
    detail = your_turn(api, created["id"])

    assert detail["status"] == "running"
    assert (detail["step"], detail["current_step"]) == ("intake", "intake")
    assert detail["park_seq"] == run["run"]["park_seq"]
    assert detail["repo_tag"] == [hub.repository_slug]
    intake = step_of(detail, "intake")
    assert intake["kind"] == "conversation"
    assert intake["status"] == "running"
    assert intake["run_id"] == run_id
    assert intake["park_kind"] == "conversation"
    assert intake["park_seq"] == run["run"]["park_seq"]
    assert [turn["message"] for turn in intake["turns"]] == [FIRST_MESSAGE]
    assert intake["turns"][0]["author"] == "operator"
    assert intake["turns"][0]["status"] == "done"
    assert step_of(detail, "product")["status"] == "planned"
    assert detail["owners"] == []
    assert [(s["kind"], s["id"]) for s in detail["sessions"]][:1] == [("run", run_id)]

    assert run["initiative"] == {
        "id": created["id"],
        "slug": created["slug"],
        "step": "intake",
        "position": 1,
        "workflow_count": 1,
    }
    assert run["template_type"] == "interactive"

    board = api.get(RUNS, params={"view": "board", "project_id": hub.project_id})
    assert board.status_code == HTTP_OK, board.text
    columns = board.json()["columns"]
    assert run_id not in [card["id"] for card in columns["needs_you"]]
    [card] = [card for card in columns["running"] if card["id"] == run_id]
    assert card["attention"] == "your_turn"
    assert card["template_type"] == "interactive"
    assert card["initiative"]["id"] == created["id"]


def test_the_lists_narrow_by_project_and_filter(api: httpx.Client, hub: Hub) -> None:
    open_one = hub.new()
    gone = hub.new()
    cancelled = api.post(f"{INITIATIVES}/{gone['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    assert cancelled.status_code == HTTP_OK, cancelled.text

    def ids(params: dict[str, str], url: str = INITIATIVES) -> list[str]:
        response = api.get(url, params=params)
        assert response.status_code == HTTP_OK, response.text
        assert response.json()["next_cursor"] is None
        return [row["id"] for row in response.json()["items"]]

    narrowed = {"project_id": hub.project_id}
    assert set(ids({**narrowed, "filter": "all"})) == {open_one["id"], gone["id"]}
    assert open_one["id"] in ids(narrowed)
    assert ids({**narrowed, "filter": "needs_you"}) == []
    assert ids({}, f"{PROJECTS}/{hub.project_id}/initiatives") == ids(narrowed)
    assert set(ids({"filter": "all"})) >= {open_one["id"], gone["id"]}

    listed = api.get(INITIATIVES, params={**narrowed, "filter": "all"}).json()
    assert listed["columns"] == [{"workflow": "spec", "type": "interactive"}]
    assert listed["counts"]["cancelled"] == 1
    row = next(item for item in listed["items"] if item["id"] == open_one["id"])
    assert (row["project_name"], row["workflow"], row["position"]) == (
        hub.project_name,
        "spec",
        1,
    )
    assert row["workflows"] == [{"workflow": "spec", "type": "interactive", "state": "ongoing"}]


def test_the_reads_refuse_unknown_ids_and_a_bad_filter(api: httpx.Client) -> None:
    assert api.get(f"{INITIATIVES}/{UNKNOWN_ID}").status_code == HTTP_NOT_FOUND
    assert api.get(f"{PROJECTS}/{UNKNOWN_ID}/initiatives").status_code == HTTP_NOT_FOUND
    assert api.get(INITIATIVES, params={"filter": "late"}).status_code == HTTP_UNPROCESSABLE
    assert api.get(f"{INITIATIVES}/not-an-id").status_code == HTTP_UNPROCESSABLE


def test_opened_true_moves_last_opened_at_and_a_plain_read_writes_nothing(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    assert created["last_opened_at"] is None

    assert detail_of(api, created["id"])["last_opened_at"] is None
    first = detail_of(api, created["id"], opened="true")["last_opened_at"]
    assert first is not None
    assert detail_of(api, created["id"])["last_opened_at"] == first
    second = detail_of(api, created["id"], opened="true")["last_opened_at"]
    assert second >= first


# ── CAP-5: start-next ───────────────────────────────────────────────────────────────────


def test_start_next_forces_the_next_conversation_step_and_never_the_gate(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    run_id = spec_run_id(created)
    url = f"{INITIATIVES}/{created['id']}/start-next"
    stop = parked_on(api, run_id, "intake")["run"]["park_seq"]

    stale = api.post(url, json={"park_seq": stop - 1}, timeout=SIGNAL_TIMEOUT_SECONDS)
    assert stale.status_code == HTTP_CONFLICT, stale.text
    assert run_detail(api, run_id)["run"]["park_seq"] == stop

    moved = api.post(url, json={"park_seq": stop}, timeout=SIGNAL_TIMEOUT_SECONDS)
    assert moved.status_code == HTTP_OK, moved.text
    assert moved.json()["id"] == created["id"]

    product = parked_on(api, run_id, "product")
    assert next(s for s in product["steps"] if s["path"] == "intake")["status"] == "skipped"
    intake = step_of(detail_of(api, created["id"]), "intake")
    assert (intake["status"], intake["token"]) == ("skipped", "SKP")

    gate = api.post(
        url, json={"park_seq": product["run"]["park_seq"]}, timeout=SIGNAL_TIMEOUT_SECONDS
    )
    assert gate.status_code == HTTP_CONFLICT, gate.text
    assert gate.json()["detail"] == (
        "start-next refused: the next step is not a conversation step; "
        "the gate, the merge and the build are never forced"
    )
    assert run_detail(api, run_id)["run"]["park_seq"] == product["run"]["park_seq"]


def test_start_next_refuses_an_unknown_initiative_a_closed_one_and_a_bad_body(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    url = f"{INITIATIVES}/{created['id']}/start-next"
    assert api.post(url, json={"park_seq": 1, "x": 1}).status_code == HTTP_UNPROCESSABLE
    assert api.post(url, json={}).status_code == HTTP_UNPROCESSABLE
    unknown = api.post(f"{INITIATIVES}/{UNKNOWN_ID}/start-next", json={"park_seq": 1})
    assert unknown.status_code == HTTP_NOT_FOUND, unknown.text

    api.post(f"{INITIATIVES}/{created['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    closed = api.post(url, json={"park_seq": 1}, timeout=SIGNAL_TIMEOUT_SECONDS)

    assert closed.status_code == HTTP_CONFLICT, closed.text
    assert closed.json()["detail"] == "no conversation step is open"


# ── CAP-3, CAP-5: cancel ────────────────────────────────────────────────────────────────


def test_cancel_ends_the_spec_run_deletes_the_branch_and_a_second_cancel_is_refused(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    run_id = spec_run_id(created)
    parked_on(api, run_id, "intake")
    assert branch_sha(hub.url, f"spec/{created['slug']}")

    response = api.post(f"{INITIATIVES}/{created['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)

    assert response.status_code == HTTP_OK, response.text
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["cancelled_at"] is not None
    assert body["branch_cleanup_error"] is None
    assert run_detail(api, run_id)["run"]["status"] == "cancelled"
    assert branch_sha(hub.url, f"spec/{created['slug']}") == ""

    again = api.post(f"{INITIATIVES}/{created['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    assert again.status_code == HTTP_CONFLICT, again.text
    assert again.json()["detail"] == "already cancelled"
    unknown = api.post(f"{INITIATIVES}/{UNKNOWN_ID}/cancel")
    assert unknown.status_code == HTTP_NOT_FOUND, unknown.text


# ── CAP-1: the package delete waits for open initiatives ────────────────────────────────


def test_the_package_delete_is_refused_while_an_initiative_is_open(
    api: httpx.Client, hub: Hub
) -> None:
    created = hub.new()
    url = f"{PROJECTS}/{hub.project_id}/package"

    refused = api.delete(url)

    assert refused.status_code == HTTP_CONFLICT, refused.text
    assert refused.json()["detail"] == (
        f"refused: 1 open initiatives use this package — {created['slug']}"
    )
    assert api.get(url).status_code == HTTP_OK

    cancelled = api.post(f"{INITIATIVES}/{created['id']}/cancel", timeout=SIGNAL_TIMEOUT_SECONDS)
    assert cancelled.status_code == HTTP_OK, cancelled.text
    assert api.delete(url).status_code == HTTP_NO_CONTENT


# ── The surface: bearer and no MCP tool (B10) ───────────────────────────────────────────


def test_every_initiative_operation_needs_the_bearer(client: httpx.Client) -> None:
    calls = [
        ("GET", INITIATIVES),
        ("GET", f"{INITIATIVES}/{UNKNOWN_ID}"),
        ("GET", f"{PROJECTS}/{UNKNOWN_ID}/initiatives"),
        ("POST", INITIATIVES),
        ("POST", f"{INITIATIVES}/{UNKNOWN_ID}/cancel"),
        ("POST", f"{INITIATIVES}/{UNKNOWN_ID}/start-next"),
    ]
    for method, url in calls:
        assert client.request(method, url).status_code == httpx.codes.UNAUTHORIZED, (method, url)


def test_no_mcp_tool_reaches_an_initiative_operation(api: httpx.Client) -> None:
    tools = Mcp(api)._post("tools/list", {})["result"]["tools"]

    names = {tool["name"] for tool in tools}

    initiative_tools = {name for name in names if "initiative" in name}
    assert initiative_tools <= {"set_initiative_folder"}, initiative_tools
    assert not {name for name in names if "start_next" in name}
