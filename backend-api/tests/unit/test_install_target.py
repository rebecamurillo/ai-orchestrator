"""`make install` is what stands between a fresh checkout and a tooling error (AD-18).

A coding agent that finds `backend-api/.venv` or `web-client/node_modules` missing does not
see a red gate, it sees `uv: command not found` or `Cannot find module 'astro'` — a failure
it cannot act on, and one that looks like a broken story. The setup is therefore a command,
and this module pins what that command does: the recipes are read through `make -n`, which
expands variables without executing, so a dropped step fails here rather than on a machine.

The script itself is exercised in `--check` mode, which installs nothing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

MAKEFILE = REPO_ROOT / "Makefile"
#: the exit code a shell script owes a caller who typed an argument it does not accept
USAGE_ERROR = 2
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

SETUP_TARGETS = ("install", "install-e2e", "doctor")

#: every step `make install` must run, as it appears in the expanded recipe of the script
INSTALL_STEPS = (
    # the backend virtualenv, from the committed lockfile and no other resolution
    "uv sync --locked --directory backend-api",
    # the web-client tree, at the pinned pnpm, from the committed lockfile
    'corepack prepare "pnpm@${pnpm_pin}" --activate',
    "pnpm --dir web-client install --frozen-lockfile",
    # .env and .env.e2e, which `make up`, `make e2e` and the settings module all read
    "./scripts/generate-env.sh",
)


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    # MAKEFLAGS from an outer make (e.g. `make test` running pytest) would otherwise
    # leak -n/-s into this child and make the assertions meaningless.
    env = {**os.environ, "MAKEFLAGS": "", "MFLAGS": ""}
    return subprocess.run(  # fixed argv, no shell
        ["make", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


@pytest.mark.parametrize("target", SETUP_TARGETS)
def test_the_setup_targets_are_declared_and_call_the_installer(target: str) -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))
    assert target in phony.split()

    result = _make("-n", target)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "./scripts/install.sh" in result.stdout


def test_doctor_only_reports() -> None:
    """`make doctor` must never mutate the machine it is diagnosing."""
    result = _make("-n", "doctor")

    assert "--check" in result.stdout


def test_install_e2e_asks_for_the_browser_the_ui_gate_needs() -> None:
    result = _make("-n", "install-e2e")

    assert "--e2e" in result.stdout


@pytest.mark.parametrize("step", INSTALL_STEPS)
def test_the_installer_runs_every_setup_step(step: str) -> None:
    """Deleting a step must fail a test, not leave the next clone half-installed."""
    assert step in INSTALL_SH.read_text()


def test_the_installer_never_re_resolves_a_committed_lockfile() -> None:
    """A setup step that re-resolves is a setup step that can change what the gates test."""
    body = INSTALL_SH.read_text()

    assert "uv sync --locked" in body
    assert "pnpm --dir web-client install --frozen-lockfile" in body
    assert "uv sync\n" not in body
    assert "pnpm --dir web-client install\n" not in body


def test_the_installer_reads_the_pins_rather_than_copying_them() -> None:
    """A version written here twice is a version that drifts."""
    body = INSTALL_SH.read_text()

    assert "web-client/package.json" in body
    assert "backend-api/pyproject.toml" in body
    # the pinned pnpm version is never spelled out; it is read from the pin
    pnpm_pin = (
        next(
            line
            for line in (REPO_ROOT / "web-client" / "package.json").read_text().splitlines()
            if '"packageManager"' in line
        )
        .split("pnpm@")[1]
        .split('"')[0]
    )
    assert pnpm_pin not in body


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_check_mode_runs_and_names_what_is_missing() -> None:
    """The report is the deliverable: an exit code alone is not actionable."""
    result = subprocess.run(  # fixed argv, no shell
        ["bash", str(INSTALL_SH), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": os.environ.get("PATH", "")},
    )
    output = result.stdout + result.stderr

    if result.returncode == 0:
        assert "ready:" in output
    else:
        assert "setup incomplete:" in output
        # every problem line says what to do about it
        problems = [line for line in output.splitlines() if line.startswith("  - ")]
        assert problems
        for line in problems:
            assert "'" in line or "http" in line or "run 'make install'" in line


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH")
def test_an_unknown_flag_is_refused_rather_than_ignored() -> None:
    result = subprocess.run(  # fixed argv, no shell
        ["bash", str(INSTALL_SH), "--wat"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == USAGE_ERROR
    assert "usage:" in result.stderr


def test_the_installer_is_executable() -> None:
    assert Path(INSTALL_SH).stat().st_mode & 0o111
