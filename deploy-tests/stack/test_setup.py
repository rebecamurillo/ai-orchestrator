import json
import re
import secrets
import uuid

import pytest

import harness

pytestmark = pytest.mark.stack

HTTP_CREATED = 201
RELEASE_N1_TAG = harness.VERSION_2
FIXTURE_DIRECTORY = "/work/deploytest-fixtures"
RECORD = "/home/agent/.orchestrator/setup-run.json"
HARNESS_MANIFESTS = {
    "claude": "/home/agent/.claude/skills-manifest.json",
    "codex": "/home/agent/.agents/skills-manifest.json",
    "opencode": "/home/agent/.config/opencode/skills-manifest.json",
}
SKILLS_DIRS = {
    "claude": "/home/agent/.claude/skills",
    "codex": "/home/agent/.agents/skills",
}
SECRET_KEYS = (
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SESSION_SECRET",
    "ORCHESTRATOR_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "GITHUB_TOKEN",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)

SKILL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest skill fixture\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "  branch:      {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: checkout\n"
    "    uses: git.worktree\n"
    '    with: {{ base: "{{{{base_branch}}}}", branch: "{{{{branch}}}}" }}\n'
    "    gate: deterministic\n"
    "  - id: build\n"
    "    uses: agent\n"
    "    with:\n"
    "      skill: {skill}\n"
    '      args: {{ spec_folder: specs/s, story_id: "1" }}\n'
    "    prompts:\n"
    '      dispatch: "Run the skill {{skill}} in folder+id dispatch mode: spec folder'
    ' {{spec_folder}}, story id {{story_id}}."\n'
    "      rendered: >-\n"
    "        The workflow for skill {{skill}} is already rendered at {{path}}. Read that file\n"
    "        fully and follow it. Do not run render_skill.py yourself.\n"
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

MAKE_BARE_REPOSITORY = """
set -e
dir="$1"; name="$2"; manifest="$3"
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
git add --all
git commit --quiet --message seed
git push --quiet "$dir/$name.git" main:main
git --git-dir="$dir/$name.git" symbolic-ref HEAD refs/heads/main
"""

STUB_SERVER = """
import http.server, json


class Handler(http.server.BaseHTTPRequestHandler):
    def _send(self, body):
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.split("?")[0] == "/v1/models":
            self._send({"data": [{"id": "deploytest-model"}]})
        else:
            self._send({})

    def _sink(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._send({})

    do_POST = _sink
    do_PUT = _sink

    def log_message(self, *args):
        pass


http.server.ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
"""

SKILL_S_SCRIPT = """#!/usr/bin/env bash
set -eu
for dir in "$HOME/.claude/skills/s" "$HOME/.agents/skills/s"; do
  mkdir -p "$dir"
  echo "skill s" > "$dir/SKILL.md"
done
"""

LEAK_SCRIPT = """#!/usr/bin/env bash
set -eu
env
tr '\\0' '\\n' < /proc/1/environ || true
find "$HOME" -type f -readable -exec cat {} + 2>/dev/null || true
"""

FAIL_SCRIPT = """#!/usr/bin/env bash
set -eu
exit 1
for dir in "$HOME/.claude/skills/t" "$HOME/.agents/skills/t"; do
  mkdir -p "$dir"
  echo "skill t" > "$dir/SKILL.md"
done
"""

CLASH_SCRIPT = """#!/usr/bin/env bash
set -eu
echo clash > "$HOME/.claude/skills/staged-plan/SKILL.md"
mkdir -p "$HOME/.claude/skills/bmad-help"
echo clash > "$HOME/.claude/skills/bmad-help/SKILL.md"
exit 0
"""


@pytest.fixture
def _fresh_stack(runner, stack_work, installed_stack):
    # `installed_stack` reuses `stack-0-<version>` across tests; an earlier folder is moved aside
    # so this test's logs and setup folder never carry another test's leftovers.
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


@pytest.fixture
def _stub_platform(runner, stack_work, release_n):
    work = runner.mkdir(stack_work / f"stub-{uuid.uuid4().hex[:8]}")
    project = f"aio-deploy-{secrets.token_hex(4)}"
    ports = {"gateway": harness.free_port(), "tracing": harness.free_port()}
    services = "".join(
        f"  {name}:\n"
        f"    image: {release_n.backend_image}\n"
        f'    entrypoint: ["python3", "-c", {json.dumps(STUB_SERVER)}]\n'
        f'    ports: ["0.0.0.0:{port}:8080"]\n'
        for name, port in ports.items()
    )
    compose_file = runner.write(work / "compose.yml", f"services:\n{services}")
    base = ["docker", "compose", "-p", project, "-f", str(compose_file)]
    runner.check([*base, "up", "-d", "--wait", "--no-build"], cwd=work, project=project)
    yield {name: f"http://host.docker.internal:{port}" for name, port in ports.items()}
    done = runner.run([*base, "down", "-v", "--remove-orphans"], cwd=work, project=project)
    assert done.returncode == 0, f"stub teardown failed: {_tail(done)}"


def _release(runner, release_n, stack_work):
    # A fresh `work` folder: a cached default variant returns at once, an in-place rebuild is
    # the hazard story 4 names.
    return harness.build_release_n1(runner, release_n, stack_work / f"build-{uuid.uuid4().hex[:8]}")


def _tail(done):
    return (done.stdout + done.stderr).decode(errors="replace")[-2000:]


def _install_step(stack, *args):
    done = stack.install_sh(*args)
    assert done.returncode == 0, _tail(done)
    harness.wait_for_healthz(stack.client())
    return done


def _save(client, text, **fields):
    name = f"deploytest-{secrets.token_hex(4)}"
    response = client.post(
        f"/api/v1/templates/{name}/versions", json={"yaml": text.format(name=name, **fields)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def _repository(stack):
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
        MAKE_BARE_REPOSITORY,
        "sh",
        FIXTURE_DIRECTORY,
        repo_name,
        manifest,
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


def _skill_line(client, name, project_id, repository_id, harness_name):
    response = client.post(
        "/api/v1/runs/preflight",
        json={
            "template_name": name,
            "template_version": 1,
            "project_id": project_id,
            "repository_id": repository_id,
            "base_branch": "main",
            "inputs": {"branch": f"deploytest/{uuid.uuid4()}"},
            "harness": harness_name,
            "budget_usd": "5",
        },
    )
    assert response.status_code == harness.HTTP_OK, response.text
    body = response.json()
    assert body["plan_error"] is None, body["plan_error"]
    found = [line for line in body["lines"] if line["check"] == "installed skill"]
    assert len(found) == 1, body["lines"]
    return found[0]


def _record(stack):
    done = stack.compose("exec", "-T", "backend-api", "cat", RECORD)
    assert done.returncode == 0, _tail(done)
    return json.loads(done.stdout)


def _skills(stack):
    found = {}
    for name, path in HARNESS_MANIFESTS.items():
        done = stack.compose("exec", "-T", "backend-api", "cat", path)
        assert done.returncode == 0, _tail(done)
        found[name] = set(json.loads(done.stdout)["skills"])
    return found


def _setup_items(client):
    response = client.get("/api/v1/harnesses")
    assert response.status_code == harness.HTTP_OK, response.text
    return {item["name"]: item["setup"] for item in response.json()["items"]}


def _env_values(folder):
    values = {}
    for line in (folder / ".env").read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    return values


def _add_script(stack, name, text):
    stack.runner.write(stack.folder / "setup" / name, text, mode=0o755)


def _gateway_env(urls):
    return {
        "LITELLM_BASE_URL": urls["gateway"],
        "LITELLM_API_KEY": f"key-{secrets.token_hex(12)}",
        "LITELLM_SPEND_KEY": f"spend-{secrets.token_hex(12)}",
        "LANGFUSE_BASE_URL": urls["tracing"],
        "LANGFUSE_PUBLIC_KEY": f"pk-{secrets.token_hex(12)}",
        "LANGFUSE_SECRET_KEY": f"sk-{secrets.token_hex(12)}",
        "GITHUB_TOKEN": f"ghp_{secrets.token_hex(16)}",
    }


def _assert_skill_everywhere(client, skill_name, project_id, repository_id):
    template = _save(client, SKILL_TEMPLATE, skill=skill_name)
    for harness_name in SKILLS_DIRS:
        line = _skill_line(client, template, project_id, repository_id, harness_name)
        assert line["status"] == "ok", (harness_name, line)


def test_a_client_skill_reaches_claude_and_codex_after_install_upgrade_and_setup(
    runner, stack_work, release_n, _fresh_stack
):
    stack = _fresh_stack(release_n)
    _add_script(stack, "10-skill-s.sh", SKILL_S_SCRIPT)
    _install_step(stack, "--yes", "--no-pull")
    client = stack.client()
    project_id, repository_id = _repository(stack)

    def check(trigger):
        _assert_skill_everywhere(client, "s", project_id, repository_id)
        assert _record(stack)["trigger"] == trigger

    check("install")
    _release(runner, release_n, stack_work)
    _install_step(stack, "upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")
    check("upgrade")
    _install_step(stack, "setup")
    check("on-demand")

    before = (_record(stack)["at"], {n: s["at"] for n, s in _setup_items(client).items()})
    restarted = stack.compose("restart", "backend-api")
    assert restarted.returncode == 0, _tail(restarted)
    harness.wait_for_healthz(client)
    after = (_record(stack)["at"], {n: s["at"] for n, s in _setup_items(client).items()})
    assert after == before


def test_a_client_script_reads_no_secret(release_n, _fresh_stack, _stub_platform):
    stack = _fresh_stack(release_n, env=_gateway_env(_stub_platform))
    _add_script(stack, "10-leak.sh", LEAK_SCRIPT)
    secrets_held = _env_values(stack.folder)
    for key in SECRET_KEYS:
        assert secrets_held.get(key), key

    _install_step(stack, "--yes", "--no-pull")

    logs = list(stack.folder.glob("logs/setup/*/10-leak.sh.log"))
    assert len(logs) == 1, logs
    dump = logs[0].read_text(errors="replace")
    assert "ORCH_SETUP_TRIGGER=install" in dump, dump[-2000:]
    for key in SECRET_KEYS:
        assert secrets_held[key] not in dump, key


def test_a_failed_script_is_shown_and_the_instance_stays_up(release_n, _fresh_stack):
    stack = _fresh_stack(release_n)
    _add_script(stack, "20-fail.sh", FAIL_SCRIPT)
    _install_step(stack, "--yes", "--no-pull")
    client = stack.client()
    project_id, repository_id = _repository(stack)

    doctor = stack.install_sh("doctor")
    assert doctor.returncode != 0, _tail(doctor)
    assert re.search(r"^fail\s+setup\s+.*20-fail\.sh \(exit 1\)", doctor.stdout.decode(), re.M), (
        _tail(doctor)
    )
    items = _setup_items(client)
    assert items, items
    for name, setup in items.items():
        assert setup["ok"] is False, name
        assert {"script": "20-fail.sh", "reason": "exit 1"} in setup["failures"], name
    scripts = _record(stack)["scripts"]
    assert any(
        s["name"] == "20-fail.sh" and s["exit"] == 1 and s["ok"] is False for s in scripts
    ), scripts
    template = _save(client, SKILL_TEMPLATE, skill="t")
    line = _skill_line(client, template, project_id, repository_id, "claude")
    assert line["status"] == "fail", line
    assert line["text"] == "not installed: t on claude", line
    assert client.healthz().status_code == harness.HTTP_OK


def test_a_script_writing_product_skills_is_failed_and_they_are_restored(release_n, _fresh_stack):
    stack = _fresh_stack(release_n)
    _add_script(stack, "30-clash.sh", CLASH_SCRIPT)

    _install_step(stack, "--yes", "--no-pull")

    differ = stack.compose(
        "exec",
        "-T",
        "backend-api",
        "diff",
        "-r",
        "/app/ia-agents-skills/staged-plan",
        "/home/agent/.claude/skills/staged-plan",
    )
    assert differ.returncode == 0, _tail(differ)
    absent = stack.compose(
        "exec", "-T", "backend-api", "test", "-e", SKILLS_DIRS["claude"] + "/bmad-help"
    )
    assert absent.returncode != 0
    assert "bmad-help" not in _skills(stack)["claude"]
    entry = next(s for s in _record(stack)["scripts"] if s["name"] == "30-clash.sh")
    assert entry["ok"] is False, entry
    assert entry["clashes"] == ["bmad-help", "staged-plan"], entry
    for name, setup in _setup_items(stack.client()).items():
        reasons = [f["reason"] for f in setup["failures"] if f["script"] == "30-clash.sh"]
        assert len(reasons) == 1, (name, setup)
        assert "bmad-help" in reasons[0] and "staged-plan" in reasons[0], (name, reasons)


def test_a_skill_dropped_from_the_assets_is_removed_from_every_harness(release_n, _fresh_stack):
    stack = _fresh_stack(release_n)
    folder = stack.folder
    shipped = (folder / "setup" / "examples" / "copy-folder.sh").read_bytes()
    stack.runner.write(folder / "setup" / "10-copy-folder.sh", shipped, mode=0o755)
    assets = {
        "claude": folder / "setup" / "assets" / "claude" / ".claude" / "skills",
        "codex": folder / "setup" / "assets" / "codex" / ".agents" / "skills",
    }
    for skills in assets.values():
        for name in ("keep", "drop"):
            stack.runner.write(skills / name / "SKILL.md", f"skill {name}\n")

    _install_step(stack, "--yes", "--no-pull")
    found = _skills(stack)
    for harness_name in ("claude", "codex"):
        assert {"keep", "drop"} <= found[harness_name], (harness_name, found[harness_name])

    for skills in assets.values():
        stack.runner.check(["rm", "-rf", str(skills / "drop")], cwd=folder)
    _install_step(stack, "setup")

    found = _skills(stack)
    for harness_name, skills in found.items():
        assert "drop" not in skills, harness_name
    for harness_name in ("claude", "codex"):
        assert "keep" in found[harness_name], harness_name
        gone = stack.compose(
            "exec", "-T", "backend-api", "test", "-e", SKILLS_DIRS[harness_name] + "/drop"
        )
        assert gone.returncode != 0, harness_name
