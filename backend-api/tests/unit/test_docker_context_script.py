"""`scripts/docker_context.sh`: the agent's docker CLI follows VERIFY_DOCKER, both ways.

`agent-home` is a volume, so a context written by one start outlives the container; the
script must therefore remove it when the switch is off, or a Run would still reach for a
daemon the operator turned off. Two halves, like `test_readiness_fixture_script.py`: a `docker`
shim on PATH records exactly what the script asks for, and — where a real docker CLI is
installed — the real CLI is driven in a scratch `HOME` to show what `docker context ls`
answers afterwards. Context commands are local file writes; neither half contacts a daemon.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

SCRIPT = REPO_ROOT / "scripts" / "docker_context.sh"
CONTEXT = "orchestrator-dind"
ENDPOINT = "tcp://127.0.0.1:2375"

needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")

SHIM = """#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$SHIM_LOG"
"""


def run(home: Path, path: str, value: str | None) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"DOCKER_CONFIG", "DOCKER_HOST", "DOCKER_CONTEXT", "VERIFY_DOCKER"}
    }
    env.update({"HOME": str(home), "PATH": path, "SHIM_LOG": str(home / "docker.log")})
    if value is not None:
        env["VERIFY_DOCKER"] = value
    return subprocess.run(  # fixed argv, no shell
        ["bash", str(SCRIPT)], capture_output=True, text=True, env=env, check=False
    )


@pytest.fixture
def shimmed(tmp_path: Path) -> tuple[Path, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "docker").write_text(SHIM)
    (bin_dir / "docker").chmod(0o755)
    return tmp_path, f"{bin_dir}:{os.environ['PATH']}"


def calls(home: Path) -> list[str]:
    log = home / "docker.log"
    return log.read_text().splitlines() if log.is_file() else []


@needs_bash
@pytest.mark.parametrize("value", ["true", "TRUE", "1", "yes", "on"])
def test_on_writes_the_context_and_makes_it_current(shimmed: tuple[Path, str], value: str) -> None:
    home, path = shimmed

    result = run(home, path, value)

    assert result.returncode == 0, result.stderr
    assert calls(home) == [
        "context use default",
        f"context rm --force {CONTEXT}",
        f"context create {CONTEXT} --description the docker service (VERIFY_DOCKER=true) "
        f"--docker host={ENDPOINT}",
        f"context use {CONTEXT}",
    ]


@needs_bash
@pytest.mark.parametrize("value", ["false", "", "0", None])
def test_off_or_unset_removes_the_context_and_writes_none(
    shimmed: tuple[Path, str], value: str | None
) -> None:
    home, path = shimmed

    result = run(home, path, value)

    assert result.returncode == 0, result.stderr
    assert calls(home) == ["context use default", f"context rm --force {CONTEXT}"]
    assert "VERIFY_DOCKER is off" in result.stderr


@needs_bash
def test_an_image_without_the_cli_starts_anyway(tmp_path: Path) -> None:
    """An older image under a newer entrypoint must not refuse to start over docker."""
    bare = tmp_path / "bare"
    bare.mkdir()
    for tool in ("bash", "tr"):
        found = shutil.which(tool)
        assert found is not None
        (bare / tool).symlink_to(found)

    result = run(tmp_path, str(bare), "true")

    assert result.returncode == 0, result.stderr
    assert "no docker CLI" in result.stderr


# ── the real CLI, in a scratch HOME ──────────────────────────────────────────


def contexts(home: Path, docker: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in {"DOCKER_CONFIG", "DOCKER_HOST"}}
    env["HOME"] = str(home)
    return subprocess.run(  # fixed argv, no shell
        [docker, "context", "ls", "--format", "{{.Name}} {{.Current}} {{.DockerEndpoint}}"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


@needs_bash
@pytest.mark.skipif(shutil.which("docker") is None, reason="no docker CLI on this machine")
def test_the_real_cli_ends_on_the_sidecar_then_back_on_default(tmp_path: Path) -> None:
    docker = shutil.which("docker")
    assert docker is not None
    path = os.environ["PATH"]

    assert run(tmp_path, path, "true").returncode == 0
    on = contexts(tmp_path, docker).stdout.splitlines()
    assert f"{CONTEXT} true {ENDPOINT}" in on

    assert run(tmp_path, path, "false").returncode == 0
    off = contexts(tmp_path, docker).stdout.splitlines()
    assert not any(line.startswith(CONTEXT) for line in off)
    assert any(line.startswith("default true") for line in off)
