"""`deploy/install.sh` and `scripts/bundle.sh` — the client's one-command install.

The client package is a machine that has only the extracted bundle: no checkout, no `make`,
no Python. `install.sh` has to write a working `.env` from the contract on its own, and the
bundle has to carry everything the script reaches for. Neither needs Docker to prove, so
both are proved here, without it:

- **The rendered `.env` is the contract, filled.** Every variable `.env.example` declares
  is still there (the same parser `make lint` uses reads it back), every REQUIRED value is
  generated rather than a placeholder, the two spellings of the database password agree,
  and the Fernet key is one `cryptography` accepts — the placeholder is not, and a wrong
  one answers 500 on every project write.
- **The gateway and tracing start off.** Blank is the documented off switch, and `install.sh`
  writes it without a trailing comment because compose reads `NAME=  # text` as the value
  `# text`.
- **It never overwrites.** A second run leaves the file byte for byte, so re-running
  `install.sh` after a failed pull cannot rotate the token a client already uses.
- **The bundle is complete and carries no secret.** `install.sh` at the root beside
  `VERSION`, `product-files.json`, `setup/` and `kit/` inside, no `llm-platform/`; never a `.env`, whatever the working tree holds.

Shell is exercised through `bash`, skipped where there is none; the scripts are written for
bash 3.2 because that is what a stock macOS ships.

Layout revised under the Operator decision of 2026-09-30 (agent-delivery-kit plan §2): the
client install is the one directory `deploy/`, with `llm-platform/` (was `host/`) and `kit/`
(was `plugin/`) inside it, so the bundle is that directory and nothing is stitched.

Delivery revised under the Operator decision of 2026-09-30 (agent-delivery-kit plan §1 and
§10, "Retire get.sh and the release-asset job"): a release publishes the two images and a
note, and no asset — a tarball is a second copy of files the image already carries, and the
second copy is the version drift a client meets. The bootstrap comes out of the image
(`kit bootstrap | tar x`), `deploy/get.sh` — which downloaded the retired asset — is gone,
and `make bundle` stays for the offline case, sent by hand. What is pinned here is that
absence, and that the release is still created.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import stat
import subprocess
import tarfile
from pathlib import Path

import pytest
import yaml
from cryptography.fernet import Fernet

from tests.unit.conftest import REPO_ROOT, parse_env_example

DEPLOY_DIR = REPO_ROOT / "deploy"
INSTALL = DEPLOY_DIR / "install.sh"
BUNDLE = REPO_ROOT / "scripts" / "bundle.sh"
DEPLOY_ENV_EXAMPLE = DEPLOY_DIR / ".env.example"

REQUIRED = (
    "ORCHESTRATOR_TOKEN",
    "ORCHESTRATOR_SESSION_SECRET",
    "ORCHESTRATOR_SECRET_KEY",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "GITHUB_TOKEN",
)

#: `openssl rand -hex 32` — 64 hex characters; anything shorter is not what the script wrote.
TOKEN_MIN_LENGTH = 64
#: the file holds every secret of the stack, so it is readable by its owner alone
PRIVATE_MODE = 0o600

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")


def _run(
    script: Path, *args: str, cwd: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Run a script the way a client does — as a command, no shell."""
    dropped = {
        "GHCR_TOKEN",
        "GITHUB_TOKEN",
        "IMAGE_TAG",
        "LITELLM_BASE_URL",
        "LITELLM_API_KEY",
        "LITELLM_SPEND_KEY",
        "LANGFUSE_BASE_URL",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
    }
    clean = {k: v for k, v in os.environ.items() if k not in dropped}
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(script), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        env={**clean, **(env or {})},
        check=False,
    )


@pytest.fixture
def bundle_dir(tmp_path: Path) -> Path:
    """What a client has: the script and the contract, nothing else."""
    shutil.copy(INSTALL, tmp_path / "install.sh")
    shutil.copy(DEPLOY_ENV_EXAMPLE, tmp_path / ".env.example")
    return tmp_path


# ── the scripts parse ────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.parametrize("script", [INSTALL, BUNDLE])
def test_the_script_parses_and_is_executable(script: Path) -> None:
    assert script.is_file(), f"{script} is missing"
    assert script.stat().st_mode & 0o111, f"{script.name} is not executable"

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@needs_bash
def test_help_names_every_command() -> None:
    result = _run(INSTALL, "--help", cwd=DEPLOY_DIR)

    assert result.returncode == 0, result.stderr
    # `doctor`, `diagnose` and `harness` are additions (agent-delivery-kit plan §5, 2026-10-01)
    for command in (
        "start",
        "stop",
        "status",
        "logs",
        "upgrade",
        "uninstall",
        "env",
        "doctor",
        "diagnose",
        "harness",
    ):
        assert command in result.stdout, command


# ── the rendered .env ────────────────────────────────────────────────────────


@needs_bash
def test_env_renders_the_whole_contract_with_generated_secrets(bundle_dir: Path) -> None:
    result = _run(
        bundle_dir / "install.sh",
        "env",
        "--tag",
        "v9.9.9",
        "--yes",
        cwd=bundle_dir,
        env={"GHCR_TOKEN": "ghp_test"},
    )
    assert result.returncode == 0, result.stdout + result.stderr

    rendered = parse_env_example(bundle_dir / ".env")
    contract = parse_env_example(DEPLOY_ENV_EXAMPLE)

    assert set(rendered) == set(contract), sorted(set(rendered) ^ set(contract))
    # epic 3 story 2, 2026-11-11: the LLM platform leaves the product; IMAGE_TAG no longer written; setup after install
    assert "IMAGE_TAG" not in rendered
    for name in REQUIRED:
        assert rendered[name], f"{name} is blank"
        assert "change-me" not in rendered[name], f"{name} is still the placeholder"
    assert rendered["POSTGRES_PASSWORD"] in rendered["DATABASE_URL"]
    assert rendered["DATABASE_URL"].startswith("postgresql+psycopg://orchestrator:")
    assert len(rendered["ORCHESTRATOR_TOKEN"]) >= TOKEN_MIN_LENGTH
    assert rendered["GITHUB_TOKEN"] == "ghp_test"


@needs_bash
def test_the_fernet_key_is_one_the_backend_accepts(bundle_dir: Path) -> None:
    """The contract's placeholder is not a key; a wrong one fails every project write."""
    _run(bundle_dir / "install.sh", "env", "--tag", "v9.9.9", "--yes", cwd=bundle_dir)

    key = parse_env_example(bundle_dir / ".env")["ORCHESTRATOR_SECRET_KEY"]

    Fernet(key.encode())  # raises on anything that is not 32 url-safe base64 bytes


@needs_bash
def test_the_gateway_and_tracing_start_off_with_no_trailing_comment(bundle_dir: Path) -> None:
    _run(bundle_dir / "install.sh", "env", "--tag", "v9.9.9", "--yes", cwd=bundle_dir)

    lines = (bundle_dir / ".env").read_text().splitlines()

    assert "LITELLM_BASE_URL=" in lines
    assert "LANGFUSE_BASE_URL=" in lines


@needs_bash
def test_the_file_is_private_and_never_overwritten(bundle_dir: Path) -> None:
    first = _run(bundle_dir / "install.sh", "env", "--tag", "v1.0.0", "--yes", cwd=bundle_dir)
    assert first.returncode == 0, first.stderr
    written = (bundle_dir / ".env").read_bytes()

    second = _run(bundle_dir / "install.sh", "env", "--tag", "v2.0.0", "--yes", cwd=bundle_dir)

    assert second.returncode == 0, second.stderr
    assert "leaving it alone" in second.stdout
    assert (bundle_dir / ".env").read_bytes() == written
    assert stat.S_IMODE((bundle_dir / ".env").stat().st_mode) == PRIVATE_MODE


@needs_bash
def test_the_bundle_version_file_names_the_release(bundle_dir: Path) -> None:
    (bundle_dir / "VERSION").write_text("v3.1.4\n")

    result = _run(bundle_dir / "install.sh", "env", "--yes", cwd=bundle_dir)

    assert result.returncode == 0, result.stderr
    # epic 3 story 2, 2026-11-11: the LLM platform leaves the product; IMAGE_TAG no longer written; setup after install
    assert "IMAGE_TAG" not in parse_env_example(bundle_dir / ".env")


@needs_bash
def test_no_tag_anywhere_refuses_and_names_the_flag(bundle_dir: Path) -> None:
    result = _run(bundle_dir / "install.sh", "env", "--yes", cwd=bundle_dir)

    assert result.returncode != 0
    assert "--tag" in result.stderr
    assert not (bundle_dir / ".env").exists()


@needs_bash
def test_a_trailing_comment_survives_a_non_empty_value(bundle_dir: Path) -> None:
    """The contract's inline explanations stay readable in the file a client keeps."""
    _run(bundle_dir / "install.sh", "env", "--tag", "v9.9.9", "--yes", cwd=bundle_dir)

    line = next(
        line
        for line in (bundle_dir / ".env").read_text().splitlines()
        if line.startswith("ORCHESTRATOR_TOKEN=")
    )

    assert "# the one credential" in line


# ── the bundle ───────────────────────────────────────────────────────────────


@needs_bash
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_the_bundle_carries_the_installer_and_no_secret(tmp_path: Path) -> None:
    # epic 3 story 1, 2026-11-11: the package drops llm-platform/ and gains the manifest,
    # the shipped examples and the seeds.
    result = _run(BUNDLE, "v0.0.0", str(tmp_path), cwd=REPO_ROOT)
    assert result.returncode == 0, result.stdout + result.stderr

    archive = tmp_path / "ai-orchestrator-deploy-v0.0.0.tar.gz"
    assert archive.is_file()
    with tarfile.open(archive) as tar:
        members = {member.name: member for member in tar.getmembers()}
        version = tar.extractfile(members["ai-orchestrator-deploy-v0.0.0/VERSION"])
        assert version is not None
        assert version.read().decode().strip() == "v0.0.0"

    root = "ai-orchestrator-deploy-v0.0.0/"
    for path in (
        "install.sh",
        "docker-compose.yml",
        ".env.example",
        "README.md",
        "product-files.json",
        ".gitignore",
        "compose.override.yml",
        "release.env",
        "setup/bmad.choice",
        "setup/README.md",
        "setup/examples/copy-folder.sh",
        "bmad/install.sh",
        "kit/install.sh",
        "kit/skills/orchestrator/SKILL.md",
    ):
        assert root + path in members, path
        assert members[root + path].mode & 0o111 if path.endswith(".sh") else True, path
    shipped = {
        f"{root}templates/shipped/{t.name}" for t in (REPO_ROOT / "templates").glob("*.yaml")
    }
    assert shipped and shipped <= set(members)
    assert not [n for n in members if n.startswith(root + "templates/shipped/drafts")]
    assert not [n for n in members if n.startswith(root + "llm-platform")]
    assert root + ".env" not in members, ".env travelled in the bundle"
    with tarfile.open(archive) as tar:
        manifest = tar.extractfile(members[root + "product-files.json"])
        assert manifest is not None
        assert json.loads(manifest.read())["release"] == "v0.0.0"


@needs_bash
def test_the_bundle_refuses_a_tag_that_is_not_a_release(tmp_path: Path) -> None:
    result = _run(BUNDLE, "main", str(tmp_path), cwd=REPO_ROOT)

    assert result.returncode != 0
    assert not list(tmp_path.iterdir())


# ── what the script tells docker, without docker ─────────────────────────────
#
# A `docker` shim on PATH records every invocation and answers success, so the script runs
# its real control flow up to the first thing only a live stack can answer (the health
# probe). epic 3 story 2, 2026-11-11: the LLM platform leaves the product; IMAGE_TAG no longer written; setup after install.
# A client's own `llm-platform/` folder is never read, started or changed (hard rule 9).


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _rewrite(path: Path, **values: str) -> None:
    lines = []
    for line in path.read_text().splitlines():
        name = line.partition("=")[0]
        lines.append(f"{name}={values[name]}" if name in values else line)
    path.write_text("\n".join(lines) + "\n")


@pytest.fixture
def shimmed(bundle_dir: Path) -> tuple[Path, Path, dict[str, str]]:
    """A bundle with a docker shim, an installed `.env` on free ports, and a compose file."""
    shutil.copy(DEPLOY_DIR / "docker-compose.yml", bundle_dir / "docker-compose.yml")
    log = bundle_dir / "docker.log"
    shim = bundle_dir / "bin"
    shim.mkdir()
    (shim / "docker").write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\n\' "$*" >> "{log}"\n'
        '[[ "$1 $2" == "compose version" ]] && echo v2.99.0\n'
        "exit 0\n"
    )
    (shim / "docker").chmod(0o755)
    env = {"PATH": f"{shim}:{os.environ['PATH']}", "GHCR_TOKEN": "ghp_test"}
    _run(bundle_dir / "install.sh", "env", "--tag", "v9.9.9", "--yes", cwd=bundle_dir, env=env)
    _rewrite(
        bundle_dir / ".env",
        WEB_CLIENT_PORT=str(_free_port()),
        BACKEND_API_PORT=str(_free_port()),
    )
    return bundle_dir, log, env


@needs_bash
def test_a_client_llm_platform_folder_is_never_touched(
    shimmed: tuple[Path, Path, dict[str, str]],
) -> None:
    # epic 3 story 2, 2026-11-11: the LLM platform leaves the product; IMAGE_TAG no longer written; setup after install
    bundle_dir, log, env = shimmed
    host = bundle_dir / "llm-platform"
    host.mkdir()
    (host / ".env").write_text("LITELLM_PORT=4000\n")
    (host / "docker-compose.yml").write_text("services: {}\n")
    before = {p.name: p.read_bytes() for p in host.iterdir()}
    log.write_text("")

    _run(bundle_dir / "install.sh", "start", cwd=bundle_dir, env=env)
    _run(bundle_dir / "install.sh", "install", "--yes", "--no-pull", cwd=bundle_dir, env=env)

    assert "llm-platform" not in log.read_text()
    assert {p.name: p.read_bytes() for p in host.iterdir()} == before


@needs_bash
def test_no_pull_skips_the_registry_and_the_pull(
    shimmed: tuple[Path, Path, dict[str, str]],
) -> None:
    """Images built from a checkout: no token is asked for and nothing is pulled (2026-10-01)."""
    bundle_dir, log, env = shimmed
    log.write_text("")
    env = {k: v for k, v in env.items() if k != "GHCR_TOKEN"}

    result = _run(
        bundle_dir / "install.sh", "install", "--no-pull", "--yes", cwd=bundle_dir, env=env
    )

    calls = log.read_text().splitlines()
    assert not any(call.startswith("login") for call in calls), calls
    assert not any(" pull" in call for call in calls), calls
    assert any(" up " in call for call in calls), calls
    assert "GitHub token" not in result.stderr


@needs_bash
def test_a_taken_stack_port_stops_start_before_any_up(
    shimmed: tuple[Path, Path, dict[str, str]],
) -> None:
    """Something else is listening there; the script names the variable and never takes it over."""
    # epic 3 story 2, 2026-11-11: the LLM platform leaves the product; IMAGE_TAG no longer written; setup after install
    bundle_dir, log, env = shimmed
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        taken = int(holder.getsockname()[1])
        _rewrite(bundle_dir / ".env", WEB_CLIENT_PORT=str(taken))
        log.write_text("")

        result = _run(bundle_dir / "install.sh", "start", cwd=bundle_dir, env=env)

    assert result.returncode != 0
    assert "WEB_CLIENT_PORT" in result.stderr
    assert "up" not in [
        line.split()[1] for line in log.read_text().splitlines() if len(line.split()) > 1
    ]


# ── one version, reused everywhere ───────────────────────────────────────────
#
# `VERSION` at the repository root is the release number: the image tag `make push` builds,
# the name `make bundle` writes, and what release.yml checks the git tag against. A second
# place the number lived would be the drift a client meets as `manifest unknown`.

VERSION_FILE = REPO_ROOT / "VERSION"
PUSH = REPO_ROOT / "scripts" / "push-images.sh"
MAKEFILE = REPO_ROOT / "Makefile"
RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "release.yml"


def test_the_version_file_holds_one_version_and_nothing_else() -> None:
    text = VERSION_FILE.read_text()

    assert text.endswith("\n")
    assert re.fullmatch(r"\d+\.\d+\.\d+(-[0-9A-Za-z.]+)?", text.strip()), text


@needs_bash
def test_the_push_script_parses_and_is_executable() -> None:
    assert PUSH.stat().st_mode & 0o111
    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-n", str(PUSH)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


@needs_bash
@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_the_bundle_defaults_to_the_version_file(tmp_path: Path) -> None:
    result = _run(BUNDLE, "", str(tmp_path), cwd=REPO_ROOT)

    version = VERSION_FILE.read_text().strip()
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / f"ai-orchestrator-deploy-{version}.tar.gz").is_file()


def test_make_reads_the_tag_from_the_version_file() -> None:
    text = MAKEFILE.read_text()

    assert "TAG ?= $(shell cat VERSION)" in text
    assert "push:\n\t./scripts/push-images.sh $(TAG)" in text
    assert "bundle:\n\t./scripts/bundle.sh $(TAG)" in text


def test_the_release_workflow_publishes_the_version_file_not_the_git_ref() -> None:
    """Every image name comes from `verify`'s output, read off VERSION."""
    text = RELEASE_WORKFLOW.read_text()

    assert "tr -d '[:space:]' < VERSION" in text
    assert "needs.verify.outputs.tag }}-${{ matrix.arch }}" in text
    assert "github.ref_name }}-${{ matrix.arch }}" not in text


# ── the retired tarball path ─────────────────────────────────────────────────
#
# Operator decision, 2026-09-30 (agent-delivery-kit plan §1 and §10): a release attaches no
# asset and `get.sh` is gone. Both are absences, and an absence is only kept by a test that
# names it — the previous revision of this module pinned the opposite (the `bundle` job's
# `scripts/bundle.sh` call), which is the assertion these two replace.


def test_the_release_workflow_creates_the_release_and_attaches_no_bundle() -> None:
    """A note naming the images and the bootstrap; `make bundle` is sent by hand instead."""
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())

    assert "bundle" not in workflow["jobs"], sorted(workflow["jobs"])
    release = workflow["jobs"]["release"]
    assert release["permissions"]["contents"] == "write"
    assert release["if"] == "github.ref_type == 'tag'"
    script = "\n".join(step.get("run", "") for step in release["steps"])
    assert "bundle.sh" not in script
    assert "gh release upload" not in script
    assert "gh release create" in script
    assert "kit bootstrap | tar x" in script
    assert "/api/v1/kit/install.sh" in script


# spec-harness-upgrade-survives-redeploy (2026-10-29): a release bakes `.env.example`'s harness
# CLI pins into the backend image through build arguments read by a `pins` step.


@pytest.mark.parametrize("variable", ["CLAUDE_CODE_VERSION", "CODEX_VERSION", "OPENCODE_VERSION"])
def test_the_release_build_passes_each_harness_pin_from_the_pins_step(variable: str) -> None:
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())
    steps = workflow["jobs"]["build"]["steps"]
    pins_at = next(i for i, step in enumerate(steps) if step.get("id") == "pins")
    build_at, build = next(
        (i, step) for i, step in enumerate(steps) if "build-push-action" in step.get("uses", "")
    )

    assert pins_at < build_at
    assert variable in steps[pins_at]["run"]
    args = build["with"]["build-args"].splitlines()
    assert f"{variable}=${{{{ steps.pins.outputs.{variable} }}}}" in args


@needs_bash
@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ('CLAUDE_CODE_VERSION="2.1.3"  # a comment', "2.1.3"),
        ("CLAUDE_CODE_VERSION='2.1.3'", "2.1.3"),
        ("CLAUDE_CODE_VERSION=2.1.3 # one space", "2.1.3"),
        ('CLAUDE_CODE_VERSION="2.1.3', None),
        ("CLAUDE_CODE_VERSION=latest", None),
    ],
    ids=["double quotes", "single quotes", "one space", "unmatched quote", "latest"],
)
def test_the_release_pins_step_reads_a_plain_version_or_fails(
    tmp_path: Path, line: str, expected: str | None
) -> None:
    """The step's own script, run against a scratch `.env.example`."""
    workflow = yaml.safe_load(RELEASE_WORKFLOW.read_text())
    step = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("id") == "pins")
    (tmp_path / ".env.example").write_text(
        f"{line}\nCODEX_VERSION=0.152.1\nOPENCODE_VERSION=1.18.26\n"
    )
    output = tmp_path / "github_output"

    result = subprocess.run(  # fixed argv, no shell
        ["bash", "-e", "-c", step["run"]],
        capture_output=True,
        text=True,
        cwd=tmp_path,
        env={**os.environ, "GITHUB_OUTPUT": str(output)},
        check=False,
    )

    if expected is None:
        assert result.returncode != 0
        assert "CLAUDE_CODE_VERSION" in result.stdout + result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
        assert f"CLAUDE_CODE_VERSION={expected}" in output.read_text().splitlines()


def test_the_release_asset_downloader_is_gone() -> None:
    """`get.sh` read the asset with a `repo`-scoped token; nothing needs that scope now."""
    assert not (DEPLOY_DIR / "get.sh").exists()
    assert "get.sh" not in (DEPLOY_DIR / "README.md").read_text()
