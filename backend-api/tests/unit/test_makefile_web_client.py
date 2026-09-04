"""`make lint` and `make test` now decide the web-client too.

The frozen 1.1 module asserts the Python sub-gates of `lint` and the unit suite of `test`.
It cannot be extended — an existing test file is an anchor — so the sub-gates this story
adds are asserted here. Dropping `pnpm lint` from the recipe would otherwise leave eslint,
prettier, `tsc` and `astro check` unrun with both gates still green.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import _make

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

WEB_CLIENT = REPO_ROOT / "web-client"

# what `make lint` must run in web-client, as it appears in the expanded recipe
LINT_SUBGATES = ("gen:api", "--check", "run lint")


def pnpm_invocations(stdout: str) -> list[str]:
    """The expanded recipe lines that call pnpm.

    Matched on the executable's basename, the way `_uv_invocations` matches uv: `$(PNPM)`
    resolves to whatever `PNPM` holds, and a `" run "` substring filter would also match
    every `uv run` line and make the assertions below assert the wrong thing.
    """
    invocations = []
    for line in stdout.splitlines():
        tokens = line.split()
        if tokens and Path(tokens[0]).name in ("pnpm", "pnpm.cjs", "pnpm.exe"):
            invocations.append(line)
    return invocations


def _recipe(target: str) -> str:
    result = _make("-n", target)

    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


@pytest.mark.parametrize("subgate", LINT_SUBGATES)
def test_the_lint_recipe_checks_the_web_client(subgate: str) -> None:
    assert subgate in _recipe("lint")


def test_the_lint_recipe_checks_the_contract_rather_than_regenerating_it() -> None:
    """AD-3: `make lint` must report drift, not quietly repair it and report success."""
    line = next(line for line in _recipe("lint").splitlines() if "gen:api" in line)

    assert "--check" in line, line


def test_the_test_recipe_runs_the_vitest_suite() -> None:
    assert "run test" in _recipe("test")


@pytest.mark.parametrize("target", ["lint", "test"])
def test_the_web_client_steps_run_inside_the_web_client_package(target: str) -> None:
    lines = pnpm_invocations(_recipe(target))

    assert lines, _recipe(target)
    for line in lines:
        assert "--dir web-client" in line, line


def test_the_scripts_the_gates_name_exist() -> None:
    """A recipe naming a script `package.json` does not define fails only at gate time."""
    scripts = json.loads((WEB_CLIENT / "package.json").read_text())["scripts"]

    assert {"build", "e2e", "gen:api", "lint", "test", "dev", "preview"} <= set(scripts)


def test_the_unit_suite_the_gate_names_exists() -> None:
    suite = WEB_CLIENT / "tests" / "unit"
    modules = {path.name for path in suite.glob("*.test.ts")}

    assert modules >= {"lint.test.ts", "proxy.test.ts"}
