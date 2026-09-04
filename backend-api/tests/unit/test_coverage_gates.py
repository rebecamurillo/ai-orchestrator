"""The coverage half of AD-18, asserted where it can be read rather than only measured.

Three numbers decide it: 100 % branch on the two packages that hold the rules, 90 % on
changed lines, 90 % lines on the web-client modules that hold rules. A run that measures
them proves today's code; this module proves the thresholds themselves — that they are in
the recipes, that they are those numbers, and that they are met by testing the code rather
than by carving lines out of the measurement.
"""

from __future__ import annotations

import json
import shutil
import tomllib
from pathlib import Path

import pytest

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import _make

pytestmark = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")

BACKEND = REPO_ROOT / "backend-api"
WEB_CLIENT = REPO_ROOT / "web-client"
PYPROJECT = BACKEND / "pyproject.toml"
SRC = BACKEND / "src" / "orchestrator"

#: The packages AD-18 holds to 100 % branch coverage.
RULE_PACKAGES = ("domain", "application")

#: The web-client trees AD-18 holds to 90 % line coverage. `src/stores/**` has no module
#: yet; the threshold is declared so the first one lands under it.
WEB_RULE_GLOBS = ("src/lib/**", "src/stores/**")


def recipe(target: str) -> str:
    result = _make("-n", target)

    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def configuration() -> dict[str, object]:
    return tomllib.loads(PYPROJECT.read_text())["tool"]["coverage"]


def test_coverage_is_measured_over_the_whole_package_with_branches() -> None:
    run = configuration()["run"]

    assert run["branch"] is True
    assert run["source"] == ["src/orchestrator"]


def test_no_line_is_carved_out_of_the_measurement() -> None:
    """A threshold met by excluding code is not a threshold (AD-18)."""
    report = configuration()["report"]

    assert "exclude_also" not in report
    assert "exclude_lines" not in report
    assert "omit" not in configuration()["run"]


@pytest.mark.parametrize(
    "module",
    sorted(module for package in RULE_PACKAGES for module in (SRC / package).rglob("*.py")),
    ids=lambda path: str(path.relative_to(SRC)),
)
def test_no_rule_module_opts_out_of_coverage(module: Path) -> None:
    """The 100 % is reached by testing every branch, never by excluding one from the count.

    Only the two packages the threshold covers are checked: an adapter that marks an
    unreachable import fallback is a judgement about that module, not about this gate.
    """
    assert "pragma: no cover" not in module.read_text(), module.name


def test_the_test_recipe_measures_branch_coverage_and_writes_the_report() -> None:
    """`make coverage` reads `coverage.xml`; without it the changed-lines gate has no input."""
    line = next(line for line in recipe("test").splitlines() if "pytest tests/unit" in line)

    assert "--cov" in line
    assert "--cov-report=xml" in line


def test_the_test_recipe_holds_the_rule_packages_to_one_hundred_percent() -> None:
    line = next(line for line in recipe("test").splitlines() if "coverage report" in line)

    assert "--fail-under=100" in line, line
    for package in RULE_PACKAGES:
        assert f"src/orchestrator/{package}/*" in line, package


def test_the_test_recipe_measures_the_web_client_too() -> None:
    scripts = json.loads((WEB_CLIENT / "package.json").read_text())["scripts"]

    assert "run test" in recipe("test")
    assert "--coverage" in scripts["test"]


def test_the_coverage_recipe_holds_changed_lines_to_ninety_percent() -> None:
    line = next(line for line in recipe("coverage").splitlines() if "diff-cover" in line)

    assert "coverage.xml" in line
    assert "--fail-under=90" in line, line
    assert "--compare-branch" in line, line


def test_the_tools_the_recipes_name_are_pinned_dev_dependencies() -> None:
    """A recipe naming a tool the lockfile does not carry fails only at gate time."""
    dev = tomllib.loads(PYPROJECT.read_text())["dependency-groups"]["dev"]
    pinned = {entry.split("==")[0]: entry for entry in dev if "==" in entry}

    for tool in ("pytest-cov", "diff-cover", "pyyaml"):
        assert tool in pinned, tool


def test_the_web_client_coverage_provider_matches_its_test_runner() -> None:
    """`@vitest/coverage-v8` is released per vitest version; a drift breaks the run."""
    packages = json.loads((WEB_CLIENT / "package.json").read_text())["devDependencies"]

    assert packages["@vitest/coverage-v8"] == packages["vitest"]


@pytest.mark.parametrize("glob", WEB_RULE_GLOBS)
def test_the_web_client_rule_modules_are_held_to_ninety_percent_lines(glob: str) -> None:
    config = (WEB_CLIENT / "vitest.config.ts").read_text()
    thresholds = config[config.index("thresholds") :]

    assert f"'{glob}': {{ lines: 90 }}" in thresholds, glob
