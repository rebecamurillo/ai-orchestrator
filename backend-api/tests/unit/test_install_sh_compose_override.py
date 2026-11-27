"""`deploy/install.sh` reads the operator's `compose.override.yml` after the product's compose
file on every compose command, when the file is there (issue #25: a `pids_limit` or `init`
set there had no effect, since no command passed it). Release review 2026-11-26."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[3] / "deploy"
#: A `docker` that prints the arguments it was given, one per line, and succeeds.
FAKE_DOCKER = '#!/bin/sh\nfor a in "$@"; do printf "%s\\n" "$a"; done\n'


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    shutil.copy(DEPLOY / "install.sh", tmp_path / "install.sh")
    (tmp_path / "docker-compose.yml").write_text(
        "services:\n  backend-api:\n    image: ghcr.io/x/backend-api:1.0.0\n"
    )
    (tmp_path / ".env").write_text("VERIFY_DOCKER=false\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    return tmp_path


def status_arguments(folder: Path) -> list[str]:
    environment = {**os.environ, "PATH": f"{folder / 'bin'}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(  # fixed argv, no shell
        ["bash", str(folder / "install.sh"), "status"],
        cwd=folder,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.splitlines()


def test_the_override_follows_the_product_file_when_it_is_there(folder: Path) -> None:
    (folder / "compose.override.yml").write_text("services: {}\n")

    arguments = status_arguments(folder)

    files = [arguments[i + 1] for i, a in enumerate(arguments) if a == "-f"]
    assert files == [str(folder / "docker-compose.yml"), str(folder / "compose.override.yml")]


def test_without_the_override_only_the_product_file_is_read(folder: Path) -> None:
    arguments = status_arguments(folder)

    files = [arguments[i + 1] for i, a in enumerate(arguments) if a == "-f"]
    assert files == [str(folder / "docker-compose.yml")]
