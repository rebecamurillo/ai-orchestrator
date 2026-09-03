"""The gate itself is under test.

`make lint` and `make test` are what every later story is judged by, and CI does not exist
until 1.7 — so nothing but this module stands between a silently narrowed gate and a green
story. The recipes are read through `make -n`, which expands variables without executing,
so a dropped sub-gate or a dropped `--directory` fails here.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT

MAKEFILE = REPO_ROOT / "Makefile"

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

# target -> the story that makes it real
PENDING_TARGETS = {
    "e2e-ui": "1.3",
    "openapi": "1.3",
    "up": "1.6",
    "down": "1.6",
}

DECLARED_TARGETS = ("lint", "test", "e2e-api", "e2e-ui", "openapi", "up", "down")

# every sub-gate `make lint` must run, as it appears in the expanded recipe
LINT_SUBGATES = (
    "ruff check .",
    "ruff format --check .",
    "mypy src/orchestrator/domain src/orchestrator/application",
    "lint-imports",
    "check_env_contract.py",
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


def test_every_target_the_constitution_names_exists() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    for target in DECLARED_TARGETS:
        assert target in phony.split()


@pytest.mark.parametrize("subgate", LINT_SUBGATES)
def test_the_lint_recipe_runs_every_sub_gate(subgate: str) -> None:
    """Deleting a line from the lint recipe must fail a test, not pass silently."""
    result = _make("-n", "lint")

    assert result.returncode == 0, result.stdout + result.stderr
    assert subgate in result.stdout


def _uv_invocations(stdout: str) -> list[str]:
    """The expanded recipe lines that call uv.

    `$(UV)` resolves to whatever `UV` holds — inside `uv run` that is an absolute path —
    so match on the executable's basename rather than a literal prefix. Getting this wrong
    makes the assertions below vacuous instead of failing.
    """
    invocations = []
    for line in stdout.splitlines():
        tokens = line.split()
        if tokens and Path(tokens[0]).name in ("uv", "uv.exe"):
            invocations.append(line)
    return invocations


def test_the_lint_recipe_runs_inside_the_backend_package() -> None:
    """`--directory backend-api` is why `../scripts/check_env_contract.py` resolves."""
    result = _make("-n", "lint")
    invocations = _uv_invocations(result.stdout)

    assert len(invocations) == len(LINT_SUBGATES), result.stdout
    for line in invocations:
        assert "--directory backend-api" in line, line


def test_the_gates_refuse_to_re_resolve_the_committed_lockfile() -> None:
    """Without --locked a gate could rewrite the uv.lock it exists to pin."""
    result = _make("-n", "lint")
    invocations = _uv_invocations(result.stdout)

    assert invocations, result.stdout
    for line in invocations:
        assert "--locked" in line, line


def test_the_test_recipe_runs_the_unit_suite() -> None:
    result = _make("-n", "test")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "pytest tests/unit" in result.stdout


@pytest.mark.parametrize(("target", "story"), sorted(PENDING_TARGETS.items()))
def test_a_target_without_its_tooling_exits_non_zero_naming_its_story(
    target: str, story: str
) -> None:
    result = _make(target)

    assert result.returncode != 0
    assert f"not available until story {story}" in result.stdout + result.stderr
