"""The backend container gives back the PIDs its steps leave (issue #25): both stacks run an
init as PID 1 on `backend-api` and bound its PID count, and the image turns git's background
forks off. 97,046 PIDs parked a Run on 2026-11-24 and took the Docker VM's forks with them.

Read as text, for the reason `test_compose.py` gives: no YAML library is a declared
dependency of this component.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

STACKS = (REPO_ROOT / "docker-compose.yml", REPO_ROOT / "deploy" / "docker-compose.yml")
DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"
SERVICE_KEY = re.compile(r"^  [a-z][a-z-]*:\s*$")


def backend_block(path: Path) -> list[str]:
    """The lines of the `backend-api` service, up to the next service."""
    lines = path.read_text().splitlines()
    start = lines.index("  backend-api:")
    block: list[str] = []
    for line in lines[start + 1 :]:
        if SERVICE_KEY.match(line) or (line.strip() and not line.startswith(" ")):
            break
        block.append(line)
    return block


@pytest.mark.parametrize("path", STACKS, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_the_backend_runs_an_init_and_bounds_its_pids(path: Path) -> None:
    block = backend_block(path)

    assert "    init: true" in block
    limits = [line for line in block if re.fullmatch(r"    pids_limit: [1-9][0-9]*", line)]
    assert len(limits) == 1, block


def test_the_image_turns_off_git_maintenance_and_the_detached_gc() -> None:
    text = DOCKERFILE.read_text()

    assert "git config --system maintenance.auto false" in text
    assert "git config --system gc.autoDetach false" in text
