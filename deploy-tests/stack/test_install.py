import io
import json
import secrets
import tarfile
import uuid

import pytest

import harness

pytestmark = pytest.mark.stack

HTTP_CREATED = 201
RELEASE_N1_TAG = harness.VERSION_2
GATEWAY_NAMES = (
    "LITELLM_BASE_URL",
    "LITELLM_API_KEY",
    "LITELLM_SPEND_KEY",
    "LANGFUSE_BASE_URL",
    "LANGFUSE_PUBLIC_KEY",
    "LANGFUSE_SECRET_KEY",
)
SEEDS = {"compose.override.yml", "setup/bmad.choice"}
WRITTEN_DIRS = ("logs", "backups", "diagnostics", ".upgrade")
C1_PATHS = (
    "README.md",
    "VERSION",
    "install.sh",
    "docker-compose.yml",
    "release.env",
    ".env.example",
    ".gitignore",
    "product-files.json",
    "compose.override.yml",
    "bmad/install.sh",
    "bmad/README.md",
    "setup/README.md",
    "setup/examples/copy-folder.sh",
    "setup/bmad.choice",
    "templates/README.md",
)
FIXTURE_DIRECTORY = "/work/deploytest-fixtures"

SHELL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest shell-only fixture\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: first\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
    "  - id: second\n"
    "    uses: shell\n"
    "    with: {{ command: 'true' }}\n"
    "    gate: deterministic\n"
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


def _kit(runner, release, cwd):
    return runner.check(
        ["docker", "run", "--rm", "--network", "none", release.backend_image, "kit", "bootstrap"],
        cwd=cwd,
    ).stdout


def _members(kit):
    with tarfile.open(fileobj=io.BytesIO(kit)) as tar:
        return [m.name for m in tar.getmembers()], [m.name for m in tar.getmembers() if m.isfile()]


def _extract(runner, release, dest):
    kit = _kit(runner, release, runner.mkdir(dest))
    _, files = _members(kit)
    with tarfile.open(fileobj=io.BytesIO(kit)) as tar:
        tar.extractall(dest, filter="data")
    return files


def _listing(folder):
    return set(harness.snapshot(folder).keys())


def _tail(done):
    return (done.stdout + done.stderr).decode(errors="replace")[-2000:]


def _compose_ps(runner, project, cwd):
    done = runner.check(
        [
            "docker",
            "ps",
            "-a",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={project}",
        ],
        cwd=cwd,
        project=project,
    )
    return done.stdout.decode().split()


def _started_at(runner, project, cwd):
    ids = _compose_ps(runner, project, cwd)
    assert ids, f"no container in {project}"
    done = runner.check(
        ["docker", "inspect", "-f", "{{.Id}} {{.State.StartedAt}}", *sorted(ids)],
        cwd=cwd,
        project=project,
    )
    return sorted(done.stdout.decode().splitlines())


def _stub_platform(runner, release, work):
    project = f"aio-deploy-{secrets.token_hex(4)}"
    folder = runner.mkdir(work / "stubs")
    ports = {"gateway": harness.free_port(), "tracing": harness.free_port()}
    services = "".join(
        f"  {name}:\n"
        f"    image: {release.backend_image}\n"
        f'    entrypoint: ["python3", "-c", {json.dumps(STUB_SERVER)}]\n'
        f'    ports: ["0.0.0.0:{port}:8080"]\n'
        for name, port in ports.items()
    )
    compose_file = runner.write(folder / "compose.yml", f"services:\n{services}")
    runner.check(
        [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(compose_file),
            "up",
            "-d",
            "--wait",
            "--no-build",
        ],
        cwd=folder,
        project=project,
    )
    urls = {name: f"http://host.docker.internal:{port}" for name, port in ports.items()}
    return project, compose_file, urls, _started_at(runner, project, folder)


@pytest.fixture
def stub_platform(runner, stack_work, release_n):
    work = runner.mkdir(stack_work / f"stub-{uuid.uuid4().hex[:8]}")
    project, compose_file, urls, started = _stub_platform(runner, release_n, work)
    yield {"project": project, "urls": urls, "started": started, "cwd": compose_file.parent}
    done = runner.run(
        [
            "docker",
            "compose",
            "-p",
            project,
            "-f",
            str(compose_file),
            "down",
            "-v",
            "--remove-orphans",
        ],
        cwd=compose_file.parent,
        project=project,
    )
    assert done.returncode == 0, f"stub teardown failed: {_tail(done)}"


@pytest.fixture
def fresh_stack(runner, stack_work, installed_stack):
    # `installed_stack` names its folder `stack-{n}-{version}` with `n` counted per test, so
    # every test would extract over the previous test's folder (its logs/, backups/, .upgrade/,
    # llm-platform/). An earlier folder is moved aside first; this test's own are never moved.
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


def _client_platform(runner, release, folder):
    project = f"aio-deploy-{secrets.token_hex(4)}"
    base = folder / "llm-platform"
    runner.write(
        base / "docker-compose.yml",
        f"name: {project}\nservices:\n  gateway:\n    image: {release.backend_image}\n"
        '    command: ["true"]\n',
    )
    runner.write(base / ".env", "CLIENT_KEY=client-owned\n")
    runner.write(base / "README.md", "# the client's own platform\n")
    return project


def _platform_untouched(stack, project, before, outputs):
    assert harness.snapshot(stack.folder / "llm-platform") == before
    assert _compose_ps(stack.runner, project, stack.folder) == []
    for done in outputs:
        assert b"llm-platform" not in done.stdout
        assert b"llm-platform" not in done.stderr


def _install_step(stack, *args):
    done = stack.install_sh(*args) if args else stack.install()
    assert done.returncode == 0, _tail(done)
    harness.wait_for_healthz(stack.client())
    return done


def _upgrade(stack):
    return _install_step(stack, "upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")


def _save_template(client):
    name = f"deploytest-{secrets.token_hex(4)}"
    response = client.post(
        f"/api/v1/templates/{name}/versions", json={"yaml": SHELL_TEMPLATE.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def _run_fixture_template(stack, name):
    client = stack.client()
    version = client.get("/api/v1/version").json()["bmad_version"]
    manifest = f"installation:\n  version: {version}\n  installDate: 2026-09-05\nmodules: []\n"
    repo_name = str(uuid.uuid4())
    stack.runner.check(
        [
            "docker",
            "compose",
            "-p",
            stack.project,
            "--project-directory",
            str(stack.folder),
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
        ],
        cwd=stack.folder,
        project=stack.project,
    )
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
    created = client.post(
        "/api/v1/runs",
        json={
            "template_name": name,
            "template_version": 1,
            "repository_id": repository_id,
            "project_id": project_id,
            "base_branch": "main",
            "budget_usd": "5",
        },
    )
    assert created.status_code == HTTP_CREATED, created.text
    run = harness.wait_for_run(client, created.json()["run"]["id"], {"done"})
    assert run["status"] == "done", run


def test_the_archive_holds_the_folder_layout_and_ignores_the_clients_files(
    runner, stack_work, release_n
):
    dest = stack_work / "archive"
    _extract(runner, release_n, dest)
    names, files = _members(_kit(runner, release_n, dest))
    root = "ai-orchestrator/"
    assert all(not name.endswith("llm-platform") and "llm-platform" not in name for name in names)
    for path in C1_PATHS:
        assert root + path in files, path
    assert any(name.startswith(f"{root}kit/") for name in names)
    assert any(f.startswith(f"{root}templates/shipped/") and f.endswith(".yaml") for f in files)
    manifest = json.loads((dest / "ai-orchestrator" / "product-files.json").read_text())
    assert manifest["release"] == harness.VERSION_1
    assert "llm-platform" not in json.dumps(manifest)

    scratch = dest / "ignore-check"
    runner.mkdir(scratch)
    runner.check(["git", "init", "--quiet"], cwd=scratch)
    runner.write(scratch / ".gitignore", (dest / "ai-orchestrator" / ".gitignore").read_text())
    for path in (
        ".env",
        "setup/assets/x/.env",
        "backups/a",
        "logs/a",
        "diagnostics/a",
        ".upgrade/a",
    ):
        done = runner.run(["git", "check-ignore", "--no-index", "-q", path], cwd=scratch)
        assert done.returncode == 0, f"{path} is not ignored"
    done = runner.run(["git", "check-ignore", "--no-index", "-q", "templates/x.yaml"], cwd=scratch)
    assert done.returncode == 1, "templates/x.yaml is ignored"


def test_the_extracted_folder_alone_installs_upgrades_and_passes_doctor(
    runner, release_n, release_n1, fresh_stack
):
    stack = fresh_stack(release_n)
    members = {
        name.removeprefix("ai-orchestrator/")
        for name in _members(_kit(runner, release_n, stack.folder.parent))[1]
    }
    assert _listing(stack.folder) == members | {".env"}
    allowed = members | {".env"}

    def only_expected():
        extra = {
            path
            for path in _listing(stack.folder) - allowed
            if path.split("/", 1)[0] not in WRITTEN_DIRS
        }
        assert not extra, extra

    _install_step(stack)
    only_expected()
    _upgrade(stack)
    assert (stack.folder / "VERSION").read_text().strip() == release_n1.version
    only_expected()
    doctor = stack.install_sh("doctor")
    assert doctor.returncode == 0, _tail(doctor)


def _gateway_env(urls):
    return {
        "LITELLM_BASE_URL": urls["gateway"],
        "LITELLM_API_KEY": "deploytest-key",
        "LITELLM_SPEND_KEY": "deploytest-spend-key",
        "LANGFUSE_BASE_URL": urls["tracing"],
        "LANGFUSE_PUBLIC_KEY": "pk-deploytest",
        "LANGFUSE_SECRET_KEY": "sk-deploytest",
    }


def test_install_with_a_gateway_and_tracing_elsewhere_runs_a_shell_template(
    runner, release_n, release_n1, fresh_stack, stub_platform
):
    stack = fresh_stack(release_n, env=_gateway_env(stub_platform["urls"]))
    client_project = _client_platform(runner, release_n, stack.folder)
    before = harness.snapshot(stack.folder / "llm-platform")

    installed = _install_step(stack)
    _platform_untouched(stack, client_project, before, [installed])
    probe = stack.client().get("/api/v1/harnesses/codex/probe")
    assert probe.status_code == harness.HTTP_OK, probe.text
    assert probe.json()["ok"] is True, probe.json()
    assert probe.json()["models"] == ["deploytest-model"], probe.json()
    name = _save_template(stack.client())
    _run_fixture_template(stack, name)

    upgraded = _upgrade(stack)
    _platform_untouched(stack, client_project, before, [upgraded])
    _run_fixture_template(stack, name)
    assert (
        _started_at(runner, stub_platform["project"], stub_platform["cwd"])
        == (stub_platform["started"])
    )


def test_install_with_neither_gateway_nor_tracing_runs_a_shell_template(
    runner, release_n, release_n1, fresh_stack
):
    stack = fresh_stack(release_n, env=dict.fromkeys(GATEWAY_NAMES, ""))
    client_project = _client_platform(runner, release_n, stack.folder)
    before = harness.snapshot(stack.folder / "llm-platform")

    installed = _install_step(stack)
    _platform_untouched(stack, client_project, before, [installed])
    name = _save_template(stack.client())
    _run_fixture_template(stack, name)

    upgraded = _upgrade(stack)
    _platform_untouched(stack, client_project, before, [upgraded])
    _run_fixture_template(stack, name)


def test_install_into_a_kept_folder_changes_none_of_its_files(runner, release_n, fresh_stack):
    stack = fresh_stack(release_n)
    folder = stack.folder
    runner.write(
        folder / "templates" / "x.yaml",
        SHELL_TEMPLATE.format(name="x"),
    )
    runner.write(folder / "compose.override.yml", "# the client's own override\nservices: {}\n")
    runner.write(folder / "setup" / "10-a.sh", "#!/bin/sh\nexit 0\n", mode=0o755)
    before = harness.snapshot(folder)
    assert {".env", "templates/x.yaml", "compose.override.yml", "setup/10-a.sh"} <= set(before)

    done = stack.install()
    assert done.returncode == 0, _tail(done)

    after = harness.snapshot(folder)
    for path, digest in before.items():
        assert after.get(path) == digest, path
