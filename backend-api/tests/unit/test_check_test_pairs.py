"""The AD-18 rule "every `src` module has a test module", made checkable.

The gate is a script rather than a test so that it fails `make lint` — the same place a
missing `.env.example` line fails — and so that the message names the module that has no
test. What "has a test module" means is decided here: a source module is paired when some
module under the unit-test tree imports it, directly or through the package `__init__` that
re-exports it. Reachability from the composition root is deliberately not followed; every
module is reachable from `main.py`, so a rule built on that would assert nothing.

The scratch trees below are what keep the rule honest: they prove the gate fires, not just
that it passes on a repository that already satisfies it.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from check_test_pairs import main

from tests.unit.conftest import REPO_ROOT
from tests.unit.test_makefile import _make

BACKEND = REPO_ROOT / "backend-api"


def write(root: Path, relative: str, source: str = "") -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)
    return path


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A minimal package and unit-test tree, paired: `demo.thing` is imported by a test."""
    write(tmp_path, "src/demo/__init__.py")
    write(tmp_path, "src/demo/thing.py", "VALUE = 1\n")
    write(tmp_path, "tests/unit/test_thing.py", "from demo.thing import VALUE\n")
    return tmp_path


def run(tree: Path) -> int:
    return main(["--src", str(tree / "src" / "demo"), "--tests", str(tree / "tests" / "unit")])


def test_a_paired_tree_passes_and_reports_what_it_checked(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run(tree) == 0
    assert "1 module" in capsys.readouterr().out


def test_a_module_no_test_imports_fails_and_is_named(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write(tree, "src/demo/orphan.py", "VALUE = 2\n")

    assert run(tree) == 1
    captured = capsys.readouterr()
    assert "orphan.py" in captured.err
    assert "demo.orphan" in captured.err


def test_a_submodule_reached_through_its_package_re_export_is_paired(tree: Path) -> None:
    """`from demo.inner import Thing` really does execute `demo/inner/impl.py`."""
    write(tree, "src/demo/inner/__init__.py", "from demo.inner.impl import Thing\n")
    write(tree, "src/demo/inner/impl.py", "class Thing: ...\n")
    write(tree, "tests/unit/test_inner.py", "from demo.inner import Thing\n")

    assert run(tree) == 0


def test_a_package_re_export_two_hops_deep_is_still_paired(tree: Path) -> None:
    write(tree, "src/demo/outer/__init__.py", "from demo.outer.mid import Thing\n")
    write(tree, "src/demo/outer/mid/__init__.py", "from demo.outer.mid.leaf import Thing\n")
    write(tree, "src/demo/outer/mid/leaf.py", "class Thing: ...\n")
    write(tree, "tests/unit/test_outer.py", "from demo.outer import Thing\n")

    assert run(tree) == 0


def test_a_dotted_import_statement_pairs_the_module_it_names(tree: Path) -> None:
    write(tree, "src/demo/plain.py", "VALUE = 3\n")
    write(tree, "tests/unit/test_plain.py", "import demo.plain\n")

    assert run(tree) == 0


@pytest.mark.parametrize("module", ["__init__.py", "main.py"])
def test_the_composition_root_and_package_markers_are_exempt(tree: Path, module: str) -> None:
    """`main.py` wires adapters together; there is no unit for it, only the e2e stack."""
    write(tree, f"src/demo/{module}", "VALUE = 4\n")

    assert run(tree) == 0


def test_a_module_imported_only_by_another_source_module_is_not_paired(
    tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Otherwise everything `main.py` wires up would count as tested."""
    write(tree, "src/demo/main.py", "from demo.hidden import VALUE\n")
    write(tree, "src/demo/hidden.py", "VALUE = 5\n")

    assert run(tree) == 1
    assert "demo.hidden" in capsys.readouterr().err


def test_a_missing_source_tree_is_reported_rather_than_passing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--src", str(tmp_path / "nope"), "--tests", str(tmp_path)]) == 1
    assert "nope" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("make") is None, reason="make not on PATH")
def test_the_lint_recipe_runs_the_gate() -> None:
    """A gate no recipe calls is prose again. The frozen 1.1 module cannot assert this one:
    its `LINT_SUBGATES` is an anchor and its uv-invocation count is why this script runs on
    the system interpreter in the first place."""
    result = _make("-n", "lint")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "scripts/check_test_pairs.py" in result.stdout


def test_the_backend_package_satisfies_the_rule(capsys: pytest.CaptureFixture[str]) -> None:
    """The gate as `make lint` runs it, against this repository."""
    code = main(
        [
            "--src",
            str(BACKEND / "src" / "orchestrator"),
            "--tests",
            str(BACKEND / "tests" / "unit"),
        ]
    )

    assert code == 0, capsys.readouterr().err
