import base64
import dataclasses
import hashlib
import io
import os
import re
import secrets
import socket
import subprocess
import sys
import tarfile
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import guard

IMAGE_BASE = "ghcr.io/rebecamurillo/ai-orchestrator"
VERSION_1 = "0.0.0-deploytest.1"
VERSION_2 = "0.0.0-deploytest.2"
TEST_TOKEN = "deploytest-token"
HTTP_OK = 200
_SECRET_ENV = ("GHCR_TOKEN", "GITHUB_TOKEN")
_PROJECT_RE = re.compile(r"^aio-deploy-[0-9a-f]{8}$")
_IMAGE_LINE = re.compile(rf"(image:\s*{re.escape(IMAGE_BASE)}/(?:backend-api|web-client):)\S+")

STUB_BIN = """#!/usr/bin/env bash
set -euo pipefail
tools=""; dir=""
while [ $# -gt 0 ]; do
  case "$1" in
    --version) echo "stub-{letter}"; exit 0 ;;
    --tools) tools="$2"; shift 2 ;;
    --directory) dir="$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ "$tools" = claude-code ]; then base="$dir/.claude/skills"; else base="$dir/.agents/skills"; fi
for name in {names}; do
  mkdir -p "$base/$name"
  echo "{letter} $name" > "$base/$name/SKILL.md"
done
"""


class HarnessRefusal(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Release:
    version: str
    backend_image: str
    web_image: str
    changed_example: str | None
    bmad_skills: tuple[str, ...]


def _release(version: str, changed: str | None, skills: tuple[str, ...]) -> Release:
    return Release(
        version=version,
        backend_image=f"{IMAGE_BASE}/backend-api:{version}",
        web_image=f"{IMAGE_BASE}/web-client:{version}",
        changed_example=changed,
        bmad_skills=skills,
    )


class Runner:
    """The one place a process starts and a file is written."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self._admitted: set[str] = set()
        self.built_variant: dict[str, tuple[tuple[tuple[str, str], ...], str | None]] = {}

    def _inside(self, path: str | Path) -> Path:
        resolved = Path(path).resolve()
        if not resolved.is_relative_to(self.root):
            raise HarnessRefusal(f"{str(path)!r} is outside the test root {self.root}")
        return resolved

    def _admit(self, project: str) -> None:
        if project in self._admitted:
            if project in guard.FORBIDDEN_PROJECTS or not project.startswith(guard.PREFIX):
                raise guard.GuardRefusal(f"project {project!r} is not a test project")
            return
        guard.check_project(project)
        self._admitted.add(project)

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | Path,
        project: str | None = None,
        env: Mapping[str, str] | None = None,
        input: bytes | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        argv = [str(a) for a in argv]
        guard.check_argv(argv)
        for arg in argv:
            if arg == "--pull" or arg.startswith("--pull="):
                raise HarnessRefusal(f"argv {argv!r} pulls")
        guard.check_folder(cwd)
        self._inside(cwd)
        if project is not None:
            self._admit(project)
            if "-p" in argv and argv[argv.index("-p") + 1] != project:
                raise guard.GuardRefusal(f"argv {argv!r} names a project other than {project!r}")
        child = {
            k: os.environ[k]
            for k in ("PATH", "HOME", "DOCKER_HOST", "DOCKER_CONFIG")
            if k in os.environ
        }
        child.update(env or {})
        for key in child:
            if key in _SECRET_ENV or key.startswith(("LITELLM_", "LANGFUSE_")):
                raise HarnessRefusal(f"{key} is never passed to a child process")
        return subprocess.run(
            argv, cwd=str(cwd), env=child, input=input, capture_output=True, check=False
        )

    def check(self, argv: Sequence[str], **kwargs) -> subprocess.CompletedProcess[bytes]:
        done = self.run(argv, **kwargs)
        if done.returncode != 0:
            tail = (done.stderr or b"").decode(errors="replace")[-2000:]
            raise RuntimeError(f"{list(argv)!r} exited {done.returncode}: {tail}")
        return done

    def mkdir(self, path: str | Path) -> Path:
        target = self._inside(path)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def write(self, path: str | Path, data: bytes | str, mode: int | None = None) -> Path:
        target = self._inside(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data.encode() if isinstance(data, str) else data)
        if mode is not None:
            target.chmod(mode)
        return target


def bmad_package(runner: Runner, dest: Path, letter: str, names: Iterable[str]) -> Path:
    body = STUB_BIN.format(letter=letter, names=" ".join(names))
    runner.write(dest / "bin" / "bmad-method", body, mode=0o755)
    return dest


def build_context(runner: Runner, repo_root: Path, dest: Path, version: str) -> Path:
    listing = runner.check(
        [
            "git",
            "-C",
            str(repo_root),
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
        ],
        cwd=runner.root,
    ).stdout
    for raw in listing.split(b"\0"):
        if not raw:
            continue
        rel = raw.decode()
        src = Path(repo_root) / rel
        if not src.is_file():
            continue
        runner.write(dest / rel, src.read_bytes(), mode=src.stat().st_mode & 0o777)
    runner.write(dest / "VERSION", f"{version}\n")
    compose = dest / "deploy" / "docker-compose.yml"
    if compose.is_file():
        runner.write(compose, _IMAGE_LINE.sub(rf"\g<1>{version}", compose.read_text()))
    return dest


def build_release_n(runner: Runner, repo_root: Path, work: Path) -> Release:
    release = _release(VERSION_1, None, ("bmad-a1", "bmad-common"))
    ctx = build_context(runner, repo_root, runner.mkdir(work / "n" / "ctx"), VERSION_1)
    runner.check(
        ["docker", "build", "-f", "backend-api/Dockerfile", "-t", release.backend_image, str(ctx)],
        cwd=ctx,
    )
    runner.check(["docker", "build", "-t", release.web_image, str(ctx / "web-client")], cwd=ctx)
    overlay = runner.mkdir(work / "n" / "overlay")
    bmad_package(runner, overlay / "bmad-a", "A", release.bmad_skills)
    runner.write(
        overlay / "Dockerfile",
        f"FROM {release.backend_image}\n"
        "RUN find /opt/bmad -mindepth 1 -delete\n"
        "COPY --chown=agent:agent bmad-a /opt/bmad\n",
    )
    runner.check(["docker", "build", "-t", release.backend_image, str(overlay)], cwd=overlay)
    return release


def _apply_release_env(text: str, overrides: Mapping[str, str]) -> str:
    out = []
    seen = set()
    for line in text.splitlines():
        key = line.split("=", 1)[0]
        if "=" in line and key in overrides:
            out.append(f"{key}={overrides[key]}")
            seen.add(key)
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in overrides.items() if k not in seen)
    return "\n".join(out) + "\n"


def build_release_n1(
    runner: Runner,
    release_n: Release,
    work: Path,
    release_env: Mapping[str, str] | None = None,
) -> Release:
    variant = tuple(sorted((release_env or {}).items()))
    base = runner.mkdir(work / "n1")
    built = runner.built_variant.get(VERSION_2)
    if built is not None and built[0] == variant:
        return _release(VERSION_2, built[1], ("bmad-b1", "bmad-common"))
    changed: str | None = None
    created = runner.check(["docker", "create", release_n.backend_image], cwd=base)
    cid = created.stdout.decode().strip()
    try:
        runner.check(["docker", "cp", f"{cid}:/app/deploy", str(base / "deploy")], cwd=base)
        runner.check(["docker", "cp", f"{cid}:/app/VERSION", str(base / "VERSION")], cwd=base)
    finally:
        runner.run(["docker", "rm", cid], cwd=base)
    runner.write(base / "VERSION", f"{VERSION_2}\n")
    compose = base / "deploy" / "docker-compose.yml"
    runner.write(compose, _IMAGE_LINE.sub(rf"\g<1>{VERSION_2}", compose.read_text()))
    examples = sorted((base / "deploy" / "templates" / "shipped").glob("*.yaml"))
    if examples:
        runner.write(examples[0], examples[0].read_text() + "# changed in deploytest.2\n")
        changed = examples[0].stem
    if release_env:
        env_file = base / "deploy" / "release.env"
        runner.write(env_file, _apply_release_env(env_file.read_text(), release_env))
    bmad_package(runner, base / "bmad-b", "B", ("bmad-b1", "bmad-common"))
    release = _release(VERSION_2, changed, ("bmad-b1", "bmad-common"))
    runner.write(
        base / "Dockerfile",
        f"FROM {release_n.backend_image}\n"
        "RUN rm -rf /app/deploy && find /opt/bmad -mindepth 1 -delete\n"
        "COPY --chown=agent:agent VERSION /app/VERSION\n"
        "COPY --chown=agent:agent deploy /app/deploy\n"
        "COPY --chown=agent:agent bmad-b /opt/bmad\n"
        "RUN python3 /app/scripts/product_manifest.py /app/deploy /app/VERSION"
        " > /app/deploy/product-files.json\n",
    )
    runner.check(["docker", "build", "-t", release.backend_image, str(base)], cwd=base)
    runner.check(["docker", "tag", release_n.web_image, release.web_image], cwd=base)
    runner.built_variant[VERSION_2] = (variant, changed)
    return release


def remove_release_tags(runner: Runner, *releases: Release) -> None:
    for release in releases:
        for tag in (release.backend_image, release.web_image):
            if not tag.endswith((f":{VERSION_1}", f":{VERSION_2}")):
                raise HarnessRefusal(f"{tag} is not a deploytest tag")
            runner.run(["docker", "image", "rm", tag], cwd=runner.root)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self._client = httpx.Client(
            base_url=base_url, headers={"Authorization": f"Bearer {token}"}, timeout=30
        )

    def get(self, path: str, **kw) -> httpx.Response:
        return self._client.get(path, **kw)

    def post(self, path: str, **kw) -> httpx.Response:
        return self._client.post(path, **kw)

    def delete(self, path: str, **kw) -> httpx.Response:
        return self._client.delete(path, **kw)

    def healthz(self) -> httpx.Response:
        return self._client.get("/healthz")


def _set_env(text: str, values: Mapping[str, str]) -> str:
    return _apply_release_env(text, values)


@dataclasses.dataclass
class Stack:
    runner: Runner
    release: Release
    folder: Path
    project: str
    backend_port: int
    web_port: int
    token: str

    def install_sh(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return self.runner.run(
            ["./install.sh", *args],
            cwd=self.folder,
            project=self.project,
            env={"COMPOSE_PROJECT_NAME": self.project},
        )

    def install(self) -> subprocess.CompletedProcess[bytes]:
        return self.install_sh("--yes", "--no-pull")

    def compose(self, *args: str) -> subprocess.CompletedProcess[bytes]:
        return self.runner.run(
            [
                "docker",
                "compose",
                "-p",
                self.project,
                "--project-directory",
                str(self.folder),
                *args,
            ],
            cwd=self.folder,
            project=self.project,
        )

    def teardown(self) -> subprocess.CompletedProcess[bytes]:
        return self.compose(
            "--profile", "setup", "--profile", "docker", "down", "-v", "--remove-orphans"
        )

    def containers(self) -> list[str]:
        done = self.runner.check(
            [
                "docker",
                "ps",
                "-a",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
            ],
            cwd=self.folder,
            project=self.project,
        )
        return done.stdout.decode().split()

    def client(self) -> ApiClient:
        return ApiClient(f"http://127.0.0.1:{self.backend_port}", self.token)


def install_stack(
    runner: Runner, release: Release, work: Path, env: Mapping[str, str] | None = None
) -> Stack:
    work = runner.mkdir(work)
    kit = runner.check(
        ["docker", "run", "--rm", "--network", "none", release.backend_image, "kit", "bootstrap"],
        cwd=work,
    ).stdout
    runner._inside(work)
    with tarfile.open(fileobj=io.BytesIO(kit)) as tar:
        tar.extractall(work, filter="data")
    folder = work / "ai-orchestrator"
    project = f"aio-deploy-{secrets.token_hex(4)}"
    if not _PROJECT_RE.match(project):
        raise HarnessRefusal(project)
    backend_port, web_port = free_port(), free_port()
    password = secrets.token_hex(8)
    values = {
        "COMPOSE_PROJECT_NAME": project,
        "WEB_CLIENT_PORT": str(web_port),
        "BACKEND_API_PORT": str(backend_port),
        "ORCHESTRATOR_TOKEN": TEST_TOKEN,
        "ORCHESTRATOR_SESSION_SECRET": secrets.token_hex(16),
        "ORCHESTRATOR_SECRET_KEY": base64.urlsafe_b64encode(os.urandom(32)).decode(),
        "POSTGRES_PASSWORD": password,
        "DATABASE_URL": f"postgresql+psycopg://orchestrator:{password}@postgres:5432/orchestrator",
        # A fixed dummy, never a real token and never read from the host: doctor only refuses
        # a blank or `change-me` value (deploy/install.sh doctor_env), and `.env.example`'s
        # placeholder would fail AC-1's doctor (retro F1, Operator 2026-11-12).
        "GITHUB_TOKEN": "aio-deploy-test-token",
        "VERIFY_DOCKER": "false",
        "LITELLM_BASE_URL": "",
        "LITELLM_API_KEY": "",
        "LITELLM_SPEND_KEY": "",
        "LANGFUSE_BASE_URL": "",
        "LANGFUSE_PUBLIC_KEY": "",
        "LANGFUSE_SECRET_KEY": "",
        **(env or {}),
    }
    example = (folder / ".env.example").read_text()
    runner.write(folder / ".env", _set_env(example, values), mode=0o600)
    return Stack(runner, release, folder, project, backend_port, web_port, TEST_TOKEN)


def snapshot(folder: Path) -> dict[str, str]:
    root = Path(folder)
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _poll(fetch: Callable[[], tuple[bool, str]], timeout: float, what: str) -> None:
    deadline = time.monotonic() + timeout
    last = "no answer"
    while time.monotonic() < deadline:
        try:
            ok, last = fetch()
        except httpx.HTTPError as exc:
            ok, last = False, repr(exc)
        if ok:
            return
        time.sleep(2)
    raise TimeoutError(f"{what} not reached in {timeout}s; last: {last}")


def wait_for_run(
    client: ApiClient, run_id: str, statuses: Iterable[str], timeout: float = 300
) -> dict:
    wanted = set(statuses)
    body: dict = {}

    def fetch() -> tuple[bool, str]:
        nonlocal body
        resp = client.get(f"/api/v1/runs/{run_id}")
        body = resp.json() if resp.status_code == HTTP_OK else {}
        return body.get("status") in wanted, resp.text

    _poll(fetch, timeout, f"run {run_id} in {sorted(wanted)}")
    return body


def wait_for_healthz(client: ApiClient, timeout: float = 180) -> None:
    _poll(lambda: ((r := client.healthz()).status_code == HTTP_OK, r.text), timeout, "/healthz")
