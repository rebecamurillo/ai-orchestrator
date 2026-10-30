"""`npm_install_cli`: the image build is unbounded, a container start is not (Operator, 2026-10-30).

A two-minute bound on the shared line killed `npm install -g @openai/codex` during `docker build`
on an ordinary connection, and would have refused the same upgrade at container start. The build
has its own limits, so only `ensure` passes one.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

HARNESS_DIR = REPO_ROOT / "scripts" / "harness"
HARNESSES = ("claude", "codex", "opencode")
START_BOUND_SECONDS = 600
#: What the image build passes: prefix, package, version, and no bound.
BUILD_ARGUMENTS = 3


def _call(tmp_path: Path, *args: str) -> tuple[list[str], list[str]]:
    """Run `npm_install_cli` with `npm` and `timeout` shims; what each of them was asked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in (
        ("npm", f'echo "$*" >> "{tmp_path}/npm.log"\n'),
        ("timeout", f'echo "$*" >> "{tmp_path}/timeout.log"\nshift\nexec "$@"\n'),
    ):
        (bin_dir / name).write_text(f"#!/bin/sh\n{body}")
        (bin_dir / name).chmod(0o755)
    script = f'HARNESS_NAME=t; source "{HARNESS_DIR}/_common.sh"; npm_install_cli "$@"'
    subprocess.run(
        ["bash", "-c", script, "bash", *args],
        check=True,
        env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
    )
    logs = [tmp_path / "npm.log", tmp_path / "timeout.log"]
    npm, bound = (log.read_text().splitlines() if log.exists() else [] for log in logs)
    return npm, bound


def test_without_a_bound_npm_runs_directly(tmp_path: Path) -> None:
    npm, bound = _call(tmp_path, "/prefix", "pkg", "1.2.3")

    assert npm == ["install -g --prefix /prefix --fetch-retries=0 --fetch-timeout=60000 pkg@1.2.3"]
    assert bound == []


def test_with_a_bound_the_whole_install_runs_under_it(tmp_path: Path) -> None:
    npm, bound = _call(tmp_path, "/prefix", "pkg", "1.2.3", "42")

    assert len(npm) == 1
    assert len(bound) == 1
    assert bound[0].startswith("42 npm install -g ")


@pytest.mark.parametrize("harness", HARNESSES)
def test_the_image_build_passes_no_bound(harness: str) -> None:
    text = (HARNESS_DIR / f"{harness}.sh").read_text()
    call = re.search(r"^\s*npm_install_cli (.+)$", text, re.MULTILINE)

    assert call
    assert len(call.group(1).split()) == BUILD_ARGUMENTS


def test_a_container_start_passes_the_bound() -> None:
    text = (HARNESS_DIR / "_common.sh").read_text()

    assert f'npm_install_cli "$staging" "$pkg" "$pin" {START_BOUND_SECONDS}' in text


@pytest.mark.parametrize(
    "path", [REPO_ROOT / "docker-compose.yml", REPO_ROOT / "deploy" / "docker-compose.yml"]
)
def test_the_healthcheck_allows_three_bounded_installs(path: Path) -> None:
    text = path.read_text()
    start = text.index("backend-api:")
    backend = text[start : text.index("web-client:", start)]
    start_period = re.search(r"start_period: (\d+)s", backend)

    assert start_period
    assert int(start_period.group(1)) >= 3 * START_BOUND_SECONDS
