"""The gate that proves a Dockerfile still builds.

Every other gate runs from source: `make lint`, `make test` and `make coverage` never touch
Docker, `make e2e-api` starts backend-api with `python -m orchestrator.main`, and `make e2e-ui`
runs the Astro build's own output. So until this target existed, `backend-api/Dockerfile` or
`web-client/Dockerfile` could break and every gate would stay green — the failure would
surface the next time someone ran `make up`, which nothing in CI does.

Story 1.6 deferred the image build to 1.7; 1.7's brief fixed the pipeline at four jobs and
named no image build, so 1.7 correctly did not add one. This target and its job close that
gap at the operator's direction, and this module is what keeps them closed: `test_makefile.py`
is frozen and cannot be extended, and `test_ci_workflow.py` asserts the job list without
knowing why the last entry is there.

`make images` deliberately does not start anything. `make up` builds too, but only on the way
to binding three ports and a database — which a runner should not have to do to learn that a
`COPY` line is wrong.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT

MAKEFILE = REPO_ROOT / "Makefile"
COMPOSE = REPO_ROOT / "docker-compose.yml"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

DOCKERFILES = ("backend-api/Dockerfile", "web-client/Dockerfile")


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    # MAKEFLAGS from an outer make would otherwise leak -n into this child.
    env = {**os.environ, "MAKEFLAGS": "", "MFLAGS": ""}
    return subprocess.run(  # fixed argv, no shell
        ["make", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_the_target_is_declared_phony() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert "images" in phony.split()


def test_the_recipe_builds_and_starts_nothing() -> None:
    """`docker compose up --build` would bind ports; a build gate must not need any."""
    result = _make("-n", "images")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "docker compose build" in result.stdout
    for forbidden in ("up", "run", "start"):
        assert f"docker compose {forbidden}" not in result.stdout


def test_the_target_no_longer_refuses_as_an_unlanded_gate() -> None:
    """The pending-gate registry is empty; nothing may put a landed target back into it."""
    result = _make("-n", "images")

    assert "not available until story" not in result.stdout + result.stderr


@pytest.mark.parametrize("dockerfile", DOCKERFILES)
def test_the_dockerfile_is_committed(dockerfile: str) -> None:
    assert (REPO_ROOT / dockerfile).is_file(), f"{dockerfile} is missing"


def test_every_build_stanza_resolves_to_a_file_on_disk() -> None:
    """`context` and `dockerfile` are resolved the way compose resolves them.

    backend-api builds from the repository root because the image needs the shared
    `scripts/harness/`; web-client builds from its own directory. A substring assertion on
    either spelling would pass while pointing at nothing, so the pair is joined and stat-ed.
    """
    services = yaml.safe_load(COMPOSE.read_text())["services"]
    built = {name: service["build"] for name, service in services.items() if "build" in service}

    assert set(built) == {"backend-api", "web-client"}
    for name, build in built.items():
        resolved = (REPO_ROOT / build["context"] / build["dockerfile"]).resolve()
        assert resolved.is_file(), f"{name}: {resolved} does not exist"
        assert resolved.name == "Dockerfile", resolved


def test_compose_builds_rather_than_pulls_the_two_application_images() -> None:
    """An `image:` on either service would make this gate pull instead of build.

    `test_compose.py` already forbids any `image:` that is not `postgres:<n>`; this states
    the same constraint from the build gate's side, where breaking it would be silent.
    """
    text = COMPOSE.read_text()

    assert text.count("build:") == len(DOCKERFILES), "both application services build from source"
