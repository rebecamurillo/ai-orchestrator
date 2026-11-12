import hashlib
import json
import re
import secrets
import time
import uuid

import pytest

import harness

pytestmark = pytest.mark.stack

HTTP_CREATED = 201
EXIT_WORKING = 3
RELEASE_N1_TAG = harness.VERSION_2
FIXTURE_DIRECTORY = "/work/deploytest-fixtures"
HARNESS_MANIFESTS = {
    "claude": "/home/agent/.claude/skills-manifest.json",
    "codex": "/home/agent/.agents/skills-manifest.json",
    "opencode": "/home/agent/.config/opencode/skills-manifest.json",
}
_BACKEND_TAG = re.compile(r"image: .*/backend-api:(.*)")

SHELL_TEMPLATE = (
    "name: {name}\nversion: 1\ndescription: deploytest sleeping fixture\n"
    "inputs:\n"
    "  project:     {{ type: project,    required: true }}\n"
    "  repository:  {{ type: repository, required: true }}\n"
    "  base_branch: {{ type: string,     required: true }}\n"
    "steps:\n"
    "  - id: sleep\n"
    "    uses: shell\n"
    "    with: {{ command: 'sleep 120' }}\n"
    "    timeout_min: 10\n"
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


@pytest.fixture(scope="module")
def release_b(runner, stack_work, release_n):
    # Built explicitly in the default variant: another module may have rebuilt the `:2` tag.
    return harness.build_release_n1(runner, release_n, stack_work / "build")


def _tail(done):
    return (done.stdout + done.stderr).decode(errors="replace")[-2000:]


def _install_step(stack, *args):
    done = stack.install_sh(*args)
    assert done.returncode == 0, _tail(done)
    harness.wait_for_healthz(stack.client())
    return done


def _upgrade(stack):
    return _install_step(stack, "upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")


def _manifest(folder):
    data = json.loads((folder / "product-files.json").read_text())
    files = {entry["path"]: (entry["sha256"], entry["role"]) for entry in data["files"]}
    return data["release"], files


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save_template(client):
    name = f"deploytest-{secrets.token_hex(4)}"
    response = client.post(
        f"/api/v1/templates/{name}/versions", json={"yaml": SHELL_TEMPLATE.format(name=name)}
    )
    assert response.status_code == HTTP_CREATED, response.text
    return name


def _start_run(stack, name):
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
    return created.json()["run"]["id"]


def _wait_working(client, run_id, timeout=180):
    deadline = time.monotonic() + timeout
    last = "no answer"
    while time.monotonic() < deadline:
        response = client.get("/api/v1/instance/activity")
        last = response.text
        if response.status_code == harness.HTTP_OK:
            for row in response.json()["working"]:
                if row["run_id"] == run_id:
                    return row
        time.sleep(2)
    raise TimeoutError(f"run {run_id} never worked in {timeout}s; last: {last}")


def _skills(stack):
    found = {}
    for name, path in HARNESS_MANIFESTS.items():
        done = stack.compose("exec", "-T", "backend-api", "cat", path)
        assert done.returncode == 0, _tail(done)
        found[name] = set(json.loads(done.stdout)["skills"])
    return found


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


def _stored_yaml(client):
    listed = client.get("/api/v1/templates")
    assert listed.status_code == harness.HTTP_OK, listed.text
    texts = []
    for item in listed.json()["items"]:
        for version in item["versions"]:
            one = client.get(f"/api/v1/templates/{item['name']}/{version}")
            assert one.status_code == harness.HTTP_OK, one.text
            texts.append(one.json()["yaml"])
    return texts


def test_an_upgrade_replaces_product_files_only(release_n, release_b, _fresh_stack):
    stack = _fresh_stack(release_n)
    folder = stack.folder
    _install_step(stack, "--yes", "--no-pull")
    _, before_files = _manifest(folder)
    stack.runner.write(folder / "notes" / "owner.txt", "the client's own note\n")
    edited = (folder / "README.md").read_bytes() + b"a client line\n"
    stack.runner.write(folder / "README.md", edited)
    # `VERSION` is never listed in `product-files.json` (`product_manifest.py` SKIPPED_FILES),
    # yet the upgrade rewrites it: it is no client path.
    owned = {
        path: digest
        for path, digest in harness.snapshot(folder).items()
        if path not in {"product-files.json", "VERSION"}
        and before_files.get(path, ("", ""))[1] != "product"
    }
    assert {".env", "compose.override.yml", "setup/bmad.choice", "notes/owner.txt"} <= set(owned)

    done = _upgrade(stack)

    assert (folder / "VERSION").read_text().strip() == RELEASE_N1_TAG
    release, after_files = _manifest(folder)
    assert release == RELEASE_N1_TAG
    for path, (digest, role) in after_files.items():
        if role == "product":
            assert (folder / path).is_file(), path
            assert _sha(folder / path) == digest, path
    for path, digest in owned.items():
        assert _sha(folder / path) == digest, path
    previous = list(folder.glob(".upgrade/*/previous/README.md"))
    assert len(previous) == 1, previous
    assert previous[0].read_bytes() == edited
    assert "edited: README.md (your copy: .upgrade/" in done.stdout.decode()


def test_an_upgrade_is_refused_while_a_step_works(release_n, release_b, _fresh_stack):
    stack = _fresh_stack(release_n)
    folder = stack.folder
    _install_step(stack, "--yes", "--no-pull")
    client = stack.client()
    run_id = _start_run(stack, _save_template(client))
    row = _wait_working(client, run_id)

    def state():
        return (
            _backend_image(stack),
            _compose_tag(folder),
            client.get("/api/v1/version").json()["app_version"],
            harness.snapshot(folder),
        )

    before = state()
    refused = stack.install_sh("upgrade", "--tag", RELEASE_N1_TAG, "--yes", "--no-pull")

    stderr = refused.stderr.decode(errors="replace")
    assert refused.returncode == EXIT_WORKING, _tail(refused)
    assert "refused: nothing was changed" in stderr, stderr
    assert run_id in stderr, stderr
    assert f"step {row['path']}" in stderr, stderr
    assert state() == before

    finished = harness.wait_for_run(client, run_id, {"done"}, timeout=300)
    assert finished["status"] == "done", finished
    _upgrade(stack)
    assert (folder / "VERSION").read_text().strip() == RELEASE_N1_TAG


def test_an_upgrade_places_an_improved_example_beside_the_clients_copy(
    release_n, release_b, _fresh_stack
):
    example = release_b.changed_example
    assert example is not None
    stack = _fresh_stack(release_n)
    folder = stack.folder
    shipped = folder / "templates" / "shipped" / f"{example}.yaml"
    copy = folder / "templates" / f"{example}.yaml"
    stack.runner.write(copy, shipped.read_bytes())
    _install_step(stack, "--yes", "--no-pull")
    shipped_before = _sha(shipped)
    copy_before = _sha(copy)

    done = _upgrade(stack)

    assert _sha(copy) == copy_before
    _, files = _manifest(folder)
    shipped_path = f"templates/shipped/{example}.yaml"
    assert _sha(shipped) == files[shipped_path][0]
    assert _sha(shipped) != shipped_before
    assert f"improved: {shipped_path} (your copy: templates/{example}.yaml)" in (
        done.stdout.decode()
    )
    assert shipped.read_text() not in _stored_yaml(stack.client())


def test_an_upgrade_carries_bmad_forward(release_n, release_b, _fresh_stack):
    stack = _fresh_stack(release_n)
    _install_step(stack, "--yes", "--no-pull")
    for name, skills in _skills(stack).items():
        assert {"bmad-a1", "bmad-common"} <= skills, name

    _upgrade(stack)

    for name, skills in _skills(stack).items():
        assert {"bmad-b1", "bmad-common"} <= skills, name
        assert "bmad-a1" not in skills, name
    pin = re.search(r"^BMAD_VERSION=(.*)$", (stack.folder / "release.env").read_text(), re.M)
    assert pin, "release.env has no BMAD_VERSION"
    installed = stack.client().get("/api/v1/version").json()["bmad_installed"]
    assert installed == pin.group(1).strip().strip("\"'")


def test_an_upgrade_keeps_bmad_removed_until_it_is_installed_again(
    release_n, release_b, _fresh_stack
):
    stack = _fresh_stack(release_n)
    choice = stack.folder / "setup" / "bmad.choice"
    _install_step(stack, "--yes", "--no-pull")

    _install_step(stack, "bmad", "remove")
    assert choice.read_text().strip() == "removed"
    for name, skills in _skills(stack).items():
        assert not {s for s in skills if s.startswith("bmad-")}, name

    _upgrade(stack)
    assert choice.read_text().strip() == "removed"
    for name, skills in _skills(stack).items():
        assert not {s for s in skills if s.startswith("bmad-")}, name

    _install_step(stack, "bmad", "install")
    for name, skills in _skills(stack).items():
        assert {"bmad-b1", "bmad-common"} <= skills, name
        assert "bmad-a1" not in skills, name
