"""The build tools a target Repository's own commands need, in the image that runs them.

A Repository states three commands — `install_command`, `unit_test_command`,
`quality_gate_command` — and every one of them runs inside this container, in the worktree,
through `ProcessRunner`. A command the image cannot resolve exits 127, and the row parks
`misconfigured`: not a failing test, not a blocked story, just a tool that is not there. That
is the one failure a coding agent cannot act on, and the one it will try hardest to work
around — which is why the toolchain is a gate and not a README line.

Two tools are asserted here because the shipped stack itself needs them and neither arrives
with Python or Node:

- **`make`.** The Makefile is this repository's own command surface and the conventional one
  for most others; `make install` is what a Repository row most naturally states.
- **`pnpm`, through corepack.** Which pnpm a repository wants is a property of that
  repository (`packageManager` in its `package.json`), not of this image, so the version is
  never pinned here — corepack reads the pin and fetches it. Two things have to be true for
  that to work unattended: the shims must be written somewhere the non-root `agent` can
  reach (`corepack enable` defaults to the Node prefix, which is root-owned, and dies
  `EACCES`), and the download must never stop to ask, because nothing is there to answer.

Textual assertions, like `test_dockerfiles.py`'s: building the image takes minutes and
network, and `make test` has neither.
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.unit.conftest import REPO_ROOT

BACKEND_DOCKERFILE = REPO_ROOT / "backend-api" / "Dockerfile"

#: The npm prefix the image already puts on PATH and already gives to `agent`. Corepack's
#: shims go here for the same reason the harness CLIs do.
NPM_PREFIX = "/opt/npm-global"

#: The apt packages a target Repository's commands need and the base image does not carry.
REQUIRED_PACKAGES = ("make",)


def dockerfile() -> str:
    assert BACKEND_DOCKERFILE.is_file(), f"{BACKEND_DOCKERFILE} is missing"
    return BACKEND_DOCKERFILE.read_text()


def code(text: str) -> str:
    """The file with its whole-line comments dropped — prose must not satisfy a gate."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))


def line_of(text: str, needle: str) -> int:
    """Which line first holds `needle`, for the assertions about ordering."""
    for number, line in enumerate(text.splitlines()):
        if needle in line:
            return number
    raise AssertionError(f"{needle!r} is nowhere in the Dockerfile")


def test_the_image_carries_make() -> None:
    """`make install` is the commonest `install_command` there is; without it, exit 127."""
    text = code(dockerfile())

    for package in REQUIRED_PACKAGES:
        assert re.search(rf"^\s+{re.escape(package)}\s*\\?$", text, re.MULTILINE), (
            f"{package} is not in the apt install list"
        )


def test_corepack_is_enabled_where_the_agent_can_reach_it() -> None:
    """The default shim directory is the root-owned Node prefix: `agent` gets `EACCES`."""
    text = code(dockerfile())

    assert "corepack enable" in text
    assert f"corepack enable --install-directory {NPM_PREFIX}/bin" in text


def test_corepack_is_enabled_before_the_image_drops_to_the_agent_user() -> None:
    """Writing the shims is root's job; fetching the pinned pnpm is the agent's."""
    text = code(dockerfile())

    assert line_of(text, "corepack enable") < line_of(text, "USER agent")


def test_corepack_never_stops_to_ask_before_downloading() -> None:
    """It prompts on first use of a version it has not fetched. A Run cannot answer, so the
    install would hang until its own `timeout_min` killed it — a timeout park that says
    nothing about the real reason."""
    text = code(dockerfile())

    assert re.search(r"COREPACK_ENABLE_DOWNLOAD_PROMPT=0", text)


def test_the_pinned_pnpm_is_not_a_second_copy_of_a_version() -> None:
    """`corepack prepare pnpm@x.y.z` here would pin this image to one repository's choice
    and drift from every other one. The repository's own `packageManager` is the pin."""
    text = code(dockerfile())

    assert "corepack prepare" not in text
    assert not re.search(r"\bpnpm@\d", text)


def test_the_toolchain_is_not_installed_over_the_harness_layer() -> None:
    """The harness installs are last on purpose — they are the slow ones. A package layer
    added after them re-runs all three on every apt change."""
    text = code(dockerfile())

    assert line_of(text, "apt-get install") < line_of(text, "scripts/harness/claude.sh install")


def test_the_documented_scratch_path_for_corepack_stays_inside_the_agent_home() -> None:
    """`COREPACK_HOME` defaults under `$HOME`, which is the `agent-home` volume — so a
    fetched pnpm survives a restart. An image that moved it elsewhere would re-download on
    every container start, and would do it inside a Run's own `timeout_min`."""
    text = code(dockerfile())

    home = re.search(r"COREPACK_HOME=(\S+)", text)
    assert home is None or home.group(1).startswith("${AGENT_HOME}")


def test_every_required_tool_is_reachable_from_the_declared_path() -> None:
    """PATH is set once, in `ENV`; a tool installed outside it is a tool that is not there."""
    text = code(dockerfile())

    path = re.search(r"PATH=(\S+)", text)
    assert path is not None
    directories = path.group(1).split(":")
    assert f"{NPM_PREFIX}/bin" in directories
    assert "/usr/bin" in directories


def test_the_image_still_ends_as_the_non_root_user(tmp_path: Path) -> None:
    """NFR-3, asserted again here because this module adds a root `RUN` of its own."""
    users = re.findall(r"^USER\s+(\S+)", code(dockerfile()), re.MULTILINE)

    assert users[-1] == "agent"
