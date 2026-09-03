"""The gate this story lands, held to the same standard as the ones 1.1 landed.

Root `AGENTS.md` hard rule 1: the commit that retires a target's pending entry adds the test
that the landed gate actually runs. Without this module, `e2e-api` could be dropped from
`PENDING_TARGETS` and left as a recipe that does nothing, and `make test` would still be
green — the gate would have "landed" by disappearing.

`_make` and `_uv_invocations` are imported from the frozen 1.1 module rather than copied.
`_uv_invocations` matches on the executable's basename because `$(UV)` expands to an
absolute path inside `uv run`; a `startswith("uv run")` filter would match nothing and make
every assertion below vacuous. That bug shipped once already.
"""

from __future__ import annotations

import shutil

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import PENDING_TARGETS, _make, _uv_invocations

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

MAKEFILE = REPO_ROOT / "Makefile"
TARGET = "e2e-api"

# what the recipe must run, as it appears in the expanded output
E2E_SUBGATES = ("pytest tests/e2e",)


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


def test_the_recipe_actually_invokes_uv() -> None:
    """Guards the assertions below: an empty match list would make them all vacuous."""
    assert _uv_invocations(_recipe())


@pytest.mark.parametrize("subgate", E2E_SUBGATES)
def test_the_recipe_runs_the_e2e_suite(subgate: str) -> None:
    assert subgate in _recipe()


def test_the_recipe_runs_inside_the_backend_package() -> None:
    """Without `--directory backend-api` the suite and its conftest are not on the path."""
    for line in _uv_invocations(_recipe()):
        assert "--directory backend-api" in line, line


def test_the_recipe_refuses_to_re_resolve_the_committed_lockfile() -> None:
    """Without `--locked` the gate could run against a silently re-resolved dependency set."""
    for line in _uv_invocations(_recipe()):
        assert "--locked" in line, line


def test_the_recipe_does_not_run_the_unit_suite_instead() -> None:
    """`pytest tests/unit` here would make the gate green without touching the stack."""
    assert "tests/unit" not in _recipe()


def test_the_target_is_still_declared_phony() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert TARGET in phony.split()


def test_the_suite_the_gate_names_exists() -> None:
    """A recipe pointing at an absent directory would pass by collecting nothing.

    `>=`, not `==`: a later story adding an e2e module must not have to edit this file,
    which it could not do — an existing test file is an anchor.
    """
    suite = REPO_ROOT / "backend-api" / "tests" / "e2e"
    modules = {path.name for path in suite.glob("test_*.py")}

    assert suite.is_dir()
    assert modules >= {"test_smoke.py", "test_schemathesis.py", "test_migrations.py"}
