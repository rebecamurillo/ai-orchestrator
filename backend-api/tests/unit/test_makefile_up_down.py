"""The two targets this story lands, held to the same standard as the ones before them.

Root `AGENTS.md` hard rule 1: the commit that retires a target's pending entry adds the test
that the landed gate actually runs. Without this module, `up` and `down` could be dropped
from `PENDING_TARGETS` and left as recipes that do nothing — the stack would have "landed"
by disappearing, and `make test` would stay green.

`_make` is imported from the frozen 1.1 module rather than copied, the way
`test_makefile_e2e_api.py` does it. The recipes are read through `make -n`, which expands
variables without executing, so nothing here starts a container.
"""

from __future__ import annotations

import shutil

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import PENDING_TARGETS, _make

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

MAKEFILE = REPO_ROOT / "Makefile"
TARGETS = ("up", "down")


def recipe(target: str) -> str:
    result = _make("-n", target)

    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize("target", TARGETS)
def test_the_target_is_no_longer_pending(target: str) -> None:
    """The story that lands a gate is the story that retires its pending entry."""
    assert target not in PENDING_TARGETS


@pytest.mark.parametrize("target", TARGETS)
def test_the_target_no_longer_refuses(target: str) -> None:
    result = _make("-n", target)

    assert "not available until story" not in result.stdout + result.stderr


@pytest.mark.parametrize("target", TARGETS)
def test_the_target_is_still_declared_phony(target: str) -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert target in phony.split()


@pytest.mark.parametrize("target", TARGETS)
def test_the_recipe_drives_compose(target: str) -> None:
    """Anything else would be a second way to start the stack, diverging from the file."""
    assert "docker compose" in recipe(target)


def test_up_rebuilds_the_images() -> None:
    """Without `--build`, an edited Dockerfile is ignored and the Operator runs yesterday's
    image while reading today's source."""
    assert "--build" in recipe("up")


def test_up_returns_instead_of_attaching() -> None:
    """`make up` is followed by `curl`, `make e2e-api` and `docker compose exec`; an attached
    run would hold the terminal and the acceptance commands would never run."""
    assert " -d" in recipe("up")


def test_up_starts_the_whole_stack() -> None:
    """A service name here would make `make up` mean "some of it"."""
    line = next(line for line in recipe("up").splitlines() if "docker compose" in line)

    assert line.split() == ["docker", "compose", "up", "-d", "--build"], line


def test_down_stops_the_stack_without_removing_its_data() -> None:
    """`-v` here would delete `pgdata`, `work` and `agent-home` — the brief requires that
    `make down` then `make up` finds them all still there."""
    line = next(line for line in recipe("down").splitlines() if "docker compose" in line)

    assert line.split() == ["docker", "compose", "down"], line


def test_the_file_the_targets_act_on_exists() -> None:
    """A recipe pointing at an absent compose file would fail at run time, not at test time."""
    assert (REPO_ROOT / "docker-compose.yml").is_file()


def test_the_images_the_stack_builds_have_dockerfiles() -> None:
    """`docker compose up --build` is only as real as the two Dockerfiles it names."""
    assert (REPO_ROOT / "backend-api" / "Dockerfile").is_file()
    assert (REPO_ROOT / "web-client" / "Dockerfile").is_file()
