"""The durability proof is selected somewhere, and deselected everywhere it would do harm.

`tests/e2e/test_durability.py` (SPEC CAP-17, FR-12, SM-4) `SIGKILL`s the `backend-api`
container and brings it back. That makes its selection a rule rather than a convenience, and
a rule with two halves that fail in opposite directions:

- **Deselected from `make e2e-api`.** That target attaches to whatever stack is configured,
  and in CI's own `e2e-api` job the backend is a process started from source on the runner —
  there is no container to kill, and running the marker there would fail every push. So the
  recipe carries `-m`, and its default is `not durability`.
- **Selected by something.** A proof nothing runs is not a gate. `make durability` is the
  target that runs it, and the pipeline invokes that target — otherwise the one production
  defect this proof found (a start-up that crashes on every boot after the first) would be
  guarded by a command only a human types.

Both halves are asserted here, as a document and through `make -n`, the way
`tests/unit/test_e2e_isolation.py` and `tests/unit/test_ci_workflow.py` already assert the
recipes and the pipeline. Nothing here needs a docker daemon: what a daemon would add is
proof that the marker's own scenarios pass, which is what `make durability` itself is.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tomllib

import pytest
import yaml

from tests.unit.conftest import REPO_ROOT

MAKEFILE = REPO_ROOT / "Makefile"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = REPO_ROOT / "backend-api" / "pyproject.toml"
MODULE = REPO_ROOT / "backend-api" / "tests" / "e2e" / "test_durability.py"

MARKER = "durability"
TARGET = "durability"
#: What `make e2e-api` must select: everything except the marker that kills its stack.
DEFAULT_SELECTION = "not durability"

needs_make = pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")


def _make(*arguments: str) -> subprocess.CompletedProcess[str]:
    """`make -n`, with an outer make's flags cleared so `-n` is not inherited or doubled."""
    environment = {**os.environ, "MAKEFLAGS": "", "MFLAGS": ""}
    return subprocess.run(  # fixed argv, no shell
        ["make", *arguments],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=environment,
    )


def test_the_marker_is_declared_so_a_typo_in_a_selection_cannot_pass() -> None:
    """`--strict-markers` is what makes `-m "not durability"` a name and not a wish: without
    it a misspelled marker matches nothing, deselects nothing, and the gate kills its own
    stack while reporting success."""
    pytest_options = tomllib.loads(PYPROJECT.read_text())["tool"]["pytest"]["ini_options"]

    assert any(entry.split(":")[0] == MARKER for entry in pytest_options["markers"])
    assert "--strict-markers" in pytest_options["addopts"]


def test_the_module_carries_the_marker_it_is_selected_by() -> None:
    assert f"pytest.mark.{MARKER}" in MODULE.read_text()


@needs_make
def test_the_ordinary_gate_deselects_the_marker_that_kills_its_stack() -> None:
    result = _make("-n", "e2e-api")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f'-m "{DEFAULT_SELECTION}"' in result.stdout, result.stdout


@needs_make
def test_the_durability_target_selects_the_marker_and_builds_a_stack_of_its_own() -> None:
    """`make durability` is `make e2e` with the selection inverted — the same disposable
    project, the same `down -v`, reached by recursion so the two cannot drift."""
    result = _make("-n", TARGET)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"E2E_MARKER={MARKER}" in result.stdout, result.stdout
    assert " e2e" in result.stdout, result.stdout


def test_the_target_is_declared_phony() -> None:
    phony = next(line for line in MAKEFILE.read_text().splitlines() if line.startswith(".PHONY:"))

    assert TARGET in phony.split()


def test_the_pipeline_runs_the_proof() -> None:
    """A gate no automation runs is documentation. AD-18 fixes the five jobs, so this runs as
    a step of one of them rather than as a sixth."""
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    script = "\n".join(
        step.get("run", "") for job in jobs.values() for step in job.get("steps", [])
    )

    assert f"make {TARGET}" in script
