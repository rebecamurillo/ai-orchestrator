import hashlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

import guard

HARNESS = Path(__file__).resolve().parents[1] / "stack" / "harness.py"
_spec = importlib.util.spec_from_file_location("stack_harness", HARNESS)
assert _spec and _spec.loader
harness = importlib.util.module_from_spec(_spec)
sys.modules["stack_harness"] = harness
_spec.loader.exec_module(harness)

PROJECT = re.compile(r"^aio-deploy-[0-9a-f]{8}$")
IMAGES = (
    "    image: ghcr.io/rebecamurillo/ai-orchestrator/backend-api:1.0.0-beta.4\n"
    "    image: ghcr.io/rebecamurillo/ai-orchestrator/web-client:1.0.0-beta.4\n"
)

SHIM = """#!{python}
import json, os, sys
argv = sys.argv[1:]
with open({log!r}, "a") as fh:
    fh.write(json.dumps({{"argv": argv, "cwd": os.getcwd()}}) + "\\n")
if argv[:2] == ["compose", "ls"]:
    print("[]")
elif argv[:1] == ["run"] and argv[-2:] == ["kit", "bootstrap"]:
    sys.stdout.buffer.write(open({tar!r}, "rb").read())
elif argv[:1] == ["create"]:
    print("cid123")
elif argv[:1] == ["cp"]:
    src, dest = argv[1], argv[2]
    if src.endswith("/VERSION"):
        open(dest, "w").write("x\\n")
    else:
        os.makedirs(os.path.join(dest, "templates", "shipped"))
        open(os.path.join(dest, "templates", "shipped", "x.yaml"), "w").write("name: x\\n")
        open(os.path.join(dest, "docker-compose.yml"), "w").write({images!r})
        open(os.path.join(dest, "release.env"), "w").write("A_VERSION=1\\n")
"""

INSTALL_STUB = """#!/bin/sh
printf '%s|%s\\n' "$*" "$(sed -n 's/^COMPOSE_PROJECT_NAME=//p' .env)" >> install.log
"""


def _tar(path: Path) -> None:
    with tarfile.open(path, "w") as tar:
        for name, body, mode in (
            ("ai-orchestrator/.env.example", b"ORCHESTRATOR_TOKEN=\nWEB_CLIENT_PORT=1\n", 0o644),
            ("ai-orchestrator/install.sh", INSTALL_STUB.encode(), 0o755),
            ("ai-orchestrator/docker-compose.yml", IMAGES.encode(), 0o644),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(body)
            info.mode = mode
            tar.addfile(info, io.BytesIO(body))


class Rig:
    def __init__(self, tmp_path: Path, monkeypatch) -> None:
        self.base = tmp_path.resolve()
        self.root = self.base / "root"
        self.root.mkdir()
        self.log = self.base / "docker.log"
        tar = self.base / "kit.tar"
        _tar(tar)
        bin_dir = self.base / "bin"
        bin_dir.mkdir()
        shim = bin_dir / "docker"
        shim.write_text(
            SHIM.format(python=sys.executable, log=str(self.log), tar=str(tar), images=IMAGES)
        )
        shim.chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
        self.repo = self.base / "repo"
        for rel, text in {
            "VERSION": "1.0.0-beta.4\n",
            "deploy/docker-compose.yml": IMAGES,
            "deploy/release.env": "A_VERSION=1\n",
            "backend-api/Dockerfile": "FROM scratch\n",
            "web-client/Dockerfile": "FROM scratch\n",
        }.items():
            (self.repo / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.repo / rel).write_text(text)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.runner = harness.Runner(self.root)

    def records(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


@pytest.fixture
def rig(tmp_path, monkeypatch):
    return Rig(tmp_path, monkeypatch)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_whole_flow_carries_only_test_projects_and_stays_under_root(rig):
    work = rig.root / "build"
    n = harness.build_release_n(rig.runner, rig.repo, work)
    n1 = harness.build_release_n1(rig.runner, n, work)
    stack = harness.install_stack(rig.runner, n, rig.root / "stack")
    assert stack.install().returncode == 0
    assert stack.containers() == []
    stack.teardown()
    harness.remove_release_tags(rig.runner, n, n1)

    records = rig.records()
    assert records
    for rec in records:
        argv = rec["argv"]
        assert "--pull" not in argv and "login" not in argv
        assert Path(rec["cwd"]).resolve().is_relative_to(rig.root)
        if argv[0] == "compose" and argv[1] != "ls":
            assert PROJECT.match(argv[argv.index("-p") + 1])
    composes = [r for r in records if r["argv"][:1] == ["compose"] and r["argv"][1] != "ls"]
    assert composes
    line = (stack.folder / "install.log").read_text().strip()
    args, project = line.split("|")
    assert args == "--yes --no-pull"
    assert PROJECT.match(project) and project == stack.project
    assert {p.name for p in rig.base.iterdir()} == {"root", "repo", "bin", "docker.log", "kit.tar"}
    assert n1.changed_example == "x"
    dotenv = (stack.folder / ".env").read_text().splitlines()
    assert any(ln.startswith("ORCHESTRATOR_SESSION_SECRET=") for ln in dotenv)


@pytest.mark.parametrize(
    "name", ["aio", "ai-orchestrator", "aio-host", "ai-orchestrator-host", "my-stack"]
)
def test_runner_refuses_a_foreign_project_before_any_process(rig, name):
    with pytest.raises(guard.GuardRefusal):
        rig.runner.run(["docker", "compose", "-p", name, "ps"], cwd=rig.root, project=name)
    assert rig.records() == []


def test_runner_refuses_login_pull_and_outside_paths(rig):
    with pytest.raises(guard.GuardRefusal):
        rig.runner.run(["docker", "login", "ghcr.io"], cwd=rig.root)
    for argv in (["docker", "build", "--pull", "."], ["docker", "build", "--pull=true", "."]):
        with pytest.raises(harness.HarnessRefusal):
            rig.runner.run(argv, cwd=rig.root)
    with pytest.raises(harness.HarnessRefusal):
        rig.runner.run(["docker", "ps"], cwd=rig.base)
    with pytest.raises(harness.HarnessRefusal):
        rig.runner.write(rig.base / "escape", "x")
    with pytest.raises(harness.HarnessRefusal):
        rig.runner.mkdir(rig.base / "escape")
    assert rig.records() == []
    assert not (rig.base / "escape").exists()


def test_runner_refuses_an_argv_naming_another_project(rig):
    project = "aio-deploy-0123abcd"
    with pytest.raises(guard.GuardRefusal):
        rig.runner.run(["docker", "compose", "-p", "aio", "ps"], cwd=rig.root, project=project)


def test_an_admitted_project_is_not_refused_by_its_own_running_state(rig):
    project = "aio-deploy-0123abcd"
    argv = ["docker", "compose", "-p", project, "ps"]
    rig.runner.run(argv, cwd=rig.root, project=project)
    rig.runner.run(argv, cwd=rig.root, project=project)
    lists = [r for r in rig.records() if r["argv"][:2] == ["compose", "ls"]]
    assert len(lists) == 1


def test_a_running_project_is_refused_at_first_use(rig, monkeypatch):
    shim = rig.base / "bin" / "docker"
    shim.write_text('#!/bin/sh\necho \'[{"Name":"aio-deploy-0123abcd"}]\'\n')
    with pytest.raises(guard.GuardRefusal):
        rig.runner.run(["docker", "ps"], cwd=rig.root, project="aio-deploy-0123abcd")


def test_child_env_never_carries_the_developers_credentials(rig, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    done = rig.runner.run(["env"], cwd=rig.root)
    assert b"GITHUB_TOKEN" not in done.stdout
    with pytest.raises(harness.HarnessRefusal):
        rig.runner.run(["env"], cwd=rig.root, env={"LITELLM_API_KEY": "k"})


def test_build_release_n_leaves_the_working_tree_untouched(rig):
    files = ("VERSION", "deploy/docker-compose.yml", "deploy/release.env")
    before = {f: _sha(rig.repo / f) for f in files}
    harness.build_release_n(rig.runner, rig.repo, rig.root / "build")
    assert {f: _sha(rig.repo / f) for f in files} == before
    ctx = rig.root / "build" / "n" / "ctx"
    assert (ctx / "VERSION").read_text().strip() == "0.0.0-deploytest.1"
    images = [
        ln
        for ln in (ctx / "deploy" / "docker-compose.yml").read_text().splitlines()
        if "image:" in ln
    ]
    assert len(images) == len(IMAGES.splitlines()) and all(
        ln.endswith(":0.0.0-deploytest.1") for ln in images
    )


def test_n1_rebuilds_only_when_the_release_env_variant_changes(rig):
    work = rig.root / "build"
    n = harness.build_release_n(rig.runner, rig.repo, work)
    harness.build_release_n1(rig.runner, n, work)
    count = len(rig.records())
    harness.build_release_n1(rig.runner, n, work)
    assert len(rig.records()) == count
    harness.build_release_n1(rig.runner, n, work, {"A_VERSION": "2", "B_VERSION": "3"})
    assert len(rig.records()) > count
    env = (work / "n1" / "deploy" / "release.env").read_text()
    assert "A_VERSION=2" in env and "B_VERSION=3" in env and "A_VERSION=1" not in env


def test_remove_release_tags_refuses_a_non_test_tag(rig):
    foreign = harness.Release("1.0.0", "x:1.0.0", "y:1.0.0", None, ())
    with pytest.raises(harness.HarnessRefusal):
        harness.remove_release_tags(rig.runner, foreign)
    assert rig.records() == []


def test_snapshot_hashes_every_file(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f").write_text("1")
    assert harness.snapshot(tmp_path) == {"a/f": hashlib.sha256(b"1").hexdigest()}
