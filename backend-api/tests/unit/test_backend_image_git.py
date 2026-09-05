"""The one runtime dependency this story adds to the image, asserted where it can be read.

`git` is a single word in `backend-api/Dockerfile`'s apt list, and until now nothing observed
it. Delete it and every gate stays green — the unit suite drives the adapter against the
host's git, and CI runs the backend from source on a runner that has one — while the deployed
stack answers a failed line for every clone check it is ever asked to run. That is the worst
shape a dependency can have: invisible to every gate and fatal in production.

`tests/unit/test_dockerfiles.py` asserts the image's other properties and is frozen, so this
claim lives in its own module rather than beside them.
"""

from __future__ import annotations

import re

import pytest

from tests.unit.conftest import REPO_ROOT

DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"

#: The binaries the backend process itself shells out to at run time. `git` runs every clone
#: check and, from Epic 4, every worktree; `gh` is the git-host client the push and PR steps
#: use (AD-14). Neither has a Python fallback.
REQUIRED_PACKAGES = ("git",)

#: `apt-get install ... \` up to the line that ends the command.
INSTALL_BLOCK = re.compile(
    r"apt-get install[^\n]*\n(?P<packages>(?:\s+[\w.+-]+\s*\\?\n)+)", re.MULTILINE
)


@pytest.fixture(scope="module")
def dockerfile() -> str:
    assert DOCKERFILE.is_file(), f"{DOCKERFILE} does not exist"
    return DOCKERFILE.read_text()


@pytest.fixture(scope="module")
def installed_packages(dockerfile: str) -> set[str]:
    """Every package the image's apt step installs, read as a list rather than as text."""
    match = INSTALL_BLOCK.search(dockerfile)
    assert match is not None, "no `apt-get install` block found in the backend Dockerfile"
    return {word for word in match.group("packages").split() if word != "\\"}


def test_the_image_installs_packages_to_check(installed_packages: set[str]) -> None:
    """Without this, the sweep below would pass over an empty set."""
    assert installed_packages


@pytest.mark.parametrize("package", REQUIRED_PACKAGES)
def test_the_image_carries_the_binary_the_backend_shells_out_to(
    package: str, installed_packages: set[str]
) -> None:
    """A clone check with no `git` fails every line, in the one place no gate would see."""
    assert package in installed_packages, sorted(installed_packages)


def test_the_process_runs_as_the_user_that_owns_the_work_directory(dockerfile: str) -> None:
    """The clone check writes base clones under `WORK_DIR`; root would own what it wrote."""
    assert "USER agent" in dockerfile
    assert 'chown -R agent:agent "${WORK_DIR}"' in dockerfile
