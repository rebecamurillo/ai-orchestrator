import hashlib
import re
import secrets
import time
import uuid

import pytest

import harness

pytestmark = pytest.mark.stack

HTTP_CREATED = 201
EXIT_ENGINE = 4
RELEASE_N1_TAG = harness.VERSION_2
FIXTURE_DIRECTORY = "/work/deploytest-fixtures"
ANSWER = "deploytest answer"
# A parked (`needs_you`) Run holds a global slot (AD-12), so P, B and Q can only coexist as
# "two parked, one queued" with two slots; each sits on its own Repository so Q waits on the
# global ceiling and not on a partition lock.
STACK_ENV = {"ORCH_TEST_MODE": "1", "MAX_ACTIVE_RUNS": "2"}
_BACKEND_TAG = re.compile(r"image: .*/backend-api:(.*)")

_INPUTS = (
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
)

CHECKPOINT_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest parked fixture\n"
    + _INPUTS
    + "steps:\n  - id: pause\n    uses: checkpoint\n    gate: human\n"
)

AGENT_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest blocked-agent fixture\n"
    + _INPUTS
    + "  branch:      {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: checkout\n"
    "    uses: git.worktree\n"
    '    with: {{ base: "{{{{base_branch}}}}", branch: "{{{{branch}}}}" }}\n'
    "    gate: deterministic\n"
    "  - id: build\n"
    "    uses: agent\n"
    "    with:\n"
    "      harness: fake\n"
    "      skill: staged-implement\n"
    '      args: {{ spec_folder: specs/s, story_id: "1" }}\n'
    "    prompts:\n"
    '      dispatch: "Run the skill {{skill}} in folder+id dispatch mode: spec folder'
    ' {{spec_folder}}, story id {{story_id}}."\n'
    "      rendered: >-\n"
    "        The workflow for skill {{skill}} is already rendered at {{path}}. Read that file\n"
    "        fully and follow it; every step, status and halt this dispatch owes is defined\n"
    "        there. Do not run render_skill.py yourself.\n"
    "      answer: 'Answer from the operator to the blocking condition"
    ' "{{condition}}": {{answer}}\'\n'
    '      halt: "Halt after planning."\n'
    "    expect:\n"
    '      files: ["specs/s/stories/1-*.md"]\n'
    "      success: [done]\n"
    "      blocked: [blocked]\n"
    "    timeout_min: 10\n"
    "    gate: liveness\n"
)

SHELL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest queued fixture\n" + _INPUTS + "steps:\n"
    "  - id: work\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    timeout_min: 5\n"
    "    gate: deterministic\n"
)

BLOCKED_SCENARIO = """story_file:
  slug: s
  content: |
    ---
    status: blocked
    ---

    # Story 1

    ## Auto Run Result

    Status: blocked
    Blocking condition: deploytest

    Which way?
exit_code: 0
"""

DONE_SCENARIO = """story_file:
  slug: s
  content: |
    ---
    status: done
    ---

    # Story 1

    ## Auto Run Result

    Status: done
files:
  - path: DONE.md
    content: |
      done
commit: true
exit_code: 0
"""

MAKE_SCENARIO_REPOSITORY = """
set -e
dir="$1"; name="$2"; manifest="$3"; first="$4"; second="$5"
mkdir -p "$dir"
rm -rf "$dir/$name.git" "$dir/$name.seed"
git init --quiet --bare "$dir/$name.git"
git init --quiet --initial-branch=main "$dir/$name.seed"
cd "$dir/$name.seed"
git config user.email deploytest@example.invalid
git config user.name deploytest
echo "$name" > README.md
if [ -n "$manifest" ]; then
  mkdir -p _bmad/_config
  printf '%s' "$manifest" > _bmad/_config/manifest.yaml
fi
if [ -n "$first" ]; then
  mkdir -p .fake-harness/1
  printf '%s' "$first" > .fake-harness/1/attempt-1.yaml
  printf '%s' "$second" > .fake-harness/1/attempt-2.yaml
fi
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""


@pytest.fixture
def _fresh_stack(runner, stack_work, installed_stack):
    # `installed_stack` reuses `stack-0-<version>` across tests; an earlier folder is moved aside
    # so this test's snapshots never see another test's leftovers.
    made = set()

    def make(release, env=None):
        for used in sorted(stack_work.glob("stack-*")):
            if used not in made:
                moved = stack_work / f"used-{uuid.uuid4().hex[:8]}-{used.name}"
                runner.check(["mv", str(used), str(moved)], cwd=stack_work)
        stack = installed_stack(release, env)
        made.add(stack.folder.parent)
        return stack

    return make


def _release(runner, release_n, stack_work, release_env):
    # `build_release_n1` copies into `work/n1`; a rebuild into a used directory nests
    # `deploy/deploy`, so every variant gets a directory of its own.
    return harness.build_release_n1(
        runner, release_n, stack_work / f"build-{uuid.uuid4().hex[:8]}", release_env
    )


def _tail(done):
    return (done.stdout + done.stderr).decode(errors="replace")[-2000:]


def _install_step(stack, *args):
    done = stack.install_sh(*args)
    assert done.returncode == 0, _tail(done)
    harness.wait_for_healthz(stack.client())
    return done


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save(client, text):
    name = f"deploytest-{secrets.token_hex(4)}"
    response = client.post(
        f"/api/v1/templates/{name}/versions", json={"yaml": text.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def _repository(stack, scenarios=("", "")):
    client = stack.client()
    version = client.get("/api/v1/version").json()["bmad_version"]
    manifest = f"installation:\n  version: {version}\n  installDate: 2026-09-05\nmodules: []\n"
    repo_name = str(uuid.uuid4())
    made = stack.compose(
        "exec",
        "-T",
        "backend-api",
        "sh",
        "-c",
        MAKE_SCENARIO_REPOSITORY,
        "sh",
        FIXTURE_DIRECTORY,
        repo_name,
        manifest,
        scenarios[0],
        scenarios[1],
    )
    assert made.returncode == 0, _tail(made)
    project = client.post("/api/v1/projects", json={"name": f"deploytest {repo_name}"})
    assert project.status_code == HTTP_CREATED, project.text
    project_id = project.json()["id"]
    repository = client.post(
        f"/api/v1/projects/{project_id}/repositories",
        json={"url": f"file://{FIXTURE_DIRECTORY}/{repo_name}.git", "default_branch": "main"},
    )
    assert repository.status_code == HTTP_CREATED, repository.text
    repository_id = repository.json()["id"]
    check = client.post(f"/api/v1/repositories/{repository_id}/clone-check")
    assert check.status_code == harness.HTTP_OK, check.text
    assert check.json()["status"] == "ok", check.json()
    return project_id, repository_id


def _start(client, name, project_id, repository_id, inputs=None):
    created = client.post(
        "/api/v1/runs",
        json={
            "template_name": name,
            "template_version": 1,
            "repository_id": repository_id,
            "project_id": project_id,
            "base_branch": "main",
            "budget_usd": "5",
            "inputs": inputs or {},
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    return created.json()["run"]["id"]


def _detail(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/detail")
    assert response.status_code == harness.HTTP_OK, response.text
    return response.json()


def _wait_detail(client, run_id, predicate, timeout=300):
    deadline = time.monotonic() + timeout
    last = {}
    while time.monotonic() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}/detail")
        if response.status_code == harness.HTTP_OK:
            last = response.json()
            if predicate(last):
                return last
        time.sleep(2)
    rows = [(row["path"], row["status"]) for row in last.get("steps", [])]
    raise TimeoutError(f"run {run_id} not as wanted in {timeout}s; last: {rows}")


def _attempts(client, run_id):
    return {
        row["path"]: (row["status"], row["attempts"]) for row in _detail(client, run_id)["steps"]
    }


def _statuses(client, run_ids):
    return [client.get(f"/api/v1/runs/{run_id}").json()["status"] for run_id in run_ids]


def _build_blocked(detail):
    return any(
        row["path"].endswith("build") and row["status"] == "blocked" for row in detail["steps"]
    )


def _queued(client, run_id):
    response = client.get("/api/v1/instance/activity")
    if response.status_code != harness.HTTP_OK:
        return False
    body = response.json()
    row = next((r for r in body["in_engine"] if r["run_id"] == run_id), None)
    return (
        row is not None
        and row["status"] == "queued"
        and (row["queue_reason"] or "").startswith("global concurrency")
    )


def _wait_queued(client, run_id, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _queued(client, run_id):
            return
        time.sleep(2)
    raise TimeoutError(f"run {run_id} never queued behind the global ceiling in {timeout}s")


def _parked_trio(stack):
    client = stack.client()
    harnesses = client.get("/api/v1/harnesses")
    assert harnesses.status_code == harness.HTTP_OK, harnesses.text
    rows = {item["name"]: item for item in harnesses.json()["items"]}
    assert rows.get("fake", {}).get("enabled") is True, rows

    checkpoint = _save(client, CHECKPOINT_TEMPLATE)
    agent = _save(client, AGENT_TEMPLATE)
    shell = _save(client, SHELL_TEMPLATE)
    p_project, p_repository = _repository(stack)
    b_project, b_repository = _repository(stack, (BLOCKED_SCENARIO, DONE_SCENARIO))
    q_project, q_repository = _repository(stack)

    run_p = _start(client, checkpoint, p_project, p_repository)
    detail = _wait_detail(
        client,
        run_p,
        lambda d: d["alert"] is not None and d["alert"]["park_kind"] == "checkpoint",
    )
    assert detail["alert"]["park_kind"] == "checkpoint", detail["alert"]

    run_b = _start(
        client, agent, b_project, b_repository, {"branch": f"deploytest/{uuid.uuid4().hex[:8]}"}
    )
    _wait_detail(client, run_b, _build_blocked)

    run_q = _start(client, shell, q_project, q_repository)
    _wait_queued(client, run_q)

    assert _statuses(client, [run_p, run_b]) == ["needs_you", "needs_you"]
    activity = client.get("/api/v1/instance/activity").json()
    assert activity["working"] == [], activity
    in_engine = {row["run_id"] for row in activity["in_engine"]}
    assert {run_p, run_b, run_q} <= in_engine, activity
    return run_p, run_b, run_q


def _backend_image(stack):
    ident = stack.compose("ps", "-q", "backend-api").stdout.decode().strip()
    assert ident, "no backend-api container"
    done = stack.runner.check(
        ["docker", "inspect", "-f", "{{.Config.Image}}", ident],
        cwd=stack.folder,
        project=stack.project,
    )
    return done.stdout.decode().strip()


def _compose_tag(folder):
    found = _BACKEND_TAG.search((folder / "docker-compose.yml").read_text())
    assert found, "no backend-api image line"
    return found.group(1).strip()


# Runs before the default-variant test so the `:2` tag left behind is the default one, which
# `test_upgrade.py`'s `release_b` finds cached.
def test_an_engine_version_change_is_refused_while_runs_wait(
    runner, stack_work, release_n, _fresh_stack
):
    _release(runner, release_n, stack_work, {"DBOS_APPLICATION_VERSION": "2"})
    stack = _fresh_stack(release_n, STACK_ENV)
    folder = stack.folder
    _install_step(stack, "--yes", "--no-pull")
    run_p, run_b, run_q = _parked_trio(stack)
    client = stack.client()

    def state():
        return (
            _backend_image(stack),
            _compose_tag(folder),
            (folder / "VERSION").read_text(),
            client.get("/api/v1/version").json()["app_version"],
            harness.snapshot(folder),
            _statuses(client, [run_p, run_b, run_q]),
        )

    before = state()
    refused = stack.install_sh("upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")

    stderr = refused.stderr.decode(errors="replace")
    assert refused.returncode == EXIT_ENGINE, _tail(refused)
    assert "refused: nothing was changed" in stderr, stderr
    assert "changes DBOS_APPLICATION_VERSION" in stderr, stderr
    for run_id in (run_p, run_b, run_q):
        assert run_id in stderr, stderr
    assert state() == before


def test_parked_blocked_and_queued_runs_continue_after_an_upgrade(
    runner, stack_work, release_n, _fresh_stack
):
    _release(runner, release_n, stack_work, None)
    stack = _fresh_stack(release_n, STACK_ENV)
    _install_step(stack, "--yes", "--no-pull")
    run_p, run_b, run_q = _parked_trio(stack)
    client = stack.client()
    before = {run_id: _attempts(client, run_id) for run_id in (run_p, run_b, run_q)}

    done = _install_step(stack, "upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")

    stdout = done.stdout.decode(errors="replace")
    assert (stack.folder / "VERSION").read_text().strip() == RELEASE_N1_TAG
    listed = stdout.split("Runs that continue:", 1)[1]
    for run_id in (run_p, run_b, run_q):
        assert f"run {run_id}" in listed, stdout
    client = stack.client()
    harness.wait_for_healthz(client)

    continued = client.post(f"/api/v1/runs/{run_p}/signals", json={"kind": "continue"})
    assert continued.status_code == harness.HTTP_OK, continued.text
    answered = client.post(
        f"/api/v1/runs/{run_b}/signals", json={"kind": "answer", "payload": {"text": ANSWER}}
    )
    assert answered.status_code == harness.HTTP_OK, answered.text
    for run_id in (run_p, run_b, run_q):
        finished = harness.wait_for_run(client, run_id, {"done", "failed", "cancelled"})
        assert finished["status"] == "done", finished

    for run_id in (run_p, run_b, run_q):
        after = _attempts(client, run_id)
        assert set(after) == set(before[run_id]), after
        for path, (_status, count) in after.items():
            old_status, old_count = before[run_id][path]
            if run_id == run_q:
                assert count <= 1, (path, count)
            elif path.endswith("build"):
                assert count == old_count + 1, (path, old_count, count)
            elif old_status == "done":
                assert count == old_count, (path, old_count, count)
            else:
                assert count <= old_count + 1, (path, old_count, count)
