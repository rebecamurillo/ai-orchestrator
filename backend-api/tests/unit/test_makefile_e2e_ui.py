"""The `e2e-ui` gate this story lands, held to the standard 1.1 and 1.2 set.

Root `AGENTS.md` hard rule 1: the commit that retires a target's pending entry adds the
test that the landed gate actually runs. `e2e-ui` is the one gate with no `uv` in it at
all, so the checks here are about the two pnpm steps: the build must happen before
Playwright starts, because the credential spec greps `dist/`.
"""

from __future__ import annotations

import shutil

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import PENDING_TARGETS, _make
from tests.unit.test_makefile_web_client import pnpm_invocations

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

MAKEFILE = REPO_ROOT / "Makefile"
TARGET = "e2e-ui"
WEB_CLIENT = REPO_ROOT / "web-client"


def _recipe() -> str:
    result = _make("-n", TARGET)

    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_the_target_is_no_longer_pending() -> None:
    """The story that lands a gate is the story that retires its pending entry."""
    assert TARGET not in PENDING_TARGETS


def test_the_target_no_longer_refuses() -> None:
    result = _make("-n", TARGET)

    assert "not available until story" not in result.stdout + result.stderr


def test_the_recipe_builds_before_it_runs_playwright() -> None:
    """`tests/e2e/no-credential.spec.ts` greps `dist/`; without the build it greps nothing."""
    recipe = _recipe()
    build = recipe.find(" build")
    e2e = recipe.find(" e2e")

    assert build != -1, recipe
    assert e2e != -1, recipe
    assert build < e2e, recipe


def test_the_recipe_runs_the_web_client_package() -> None:
    """Without `--dir web-client` the scripts resolve against the repository root."""
    lines = pnpm_invocations(_recipe())

    assert lines, _recipe()
    for line in lines:
        assert "--dir web-client" in line, line


def test_the_recipe_does_not_run_a_python_suite_instead() -> None:
    """`pytest` here would make the gate green without ever starting a browser."""
    assert "pytest" not in _recipe()


def test_the_target_is_still_declared_phony() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert TARGET in phony.split()


def test_the_suite_the_gate_names_exists() -> None:
    """A Playwright run that collects nothing exits 0; this is what stops that passing.

    `>=`, not `==`: a later story adding a spec must not have to edit this file, which it
    could not do — an existing test file is an anchor.
    """
    suite = WEB_CLIENT / "tests" / "e2e"
    specs = {path.name for path in suite.glob("*.spec.ts")}

    assert (WEB_CLIENT / "playwright.config.ts").is_file()
    assert specs >= {"smoke.spec.ts", "no-credential.spec.ts"}


def test_playwright_supervises_its_own_server() -> None:
    """A gate that assumed a server was already up would pass by talking to anything."""
    config = (WEB_CLIENT / "playwright.config.ts").read_text()

    assert "webServer" in config
    assert "pnpm preview" in config


def test_playwright_is_pointed_at_the_committed_specs() -> None:
    """A `testDir` naming an empty directory collects nothing and still exits 0."""
    config = (WEB_CLIENT / "playwright.config.ts").read_text()

    assert "testDir: './tests/e2e'" in config
