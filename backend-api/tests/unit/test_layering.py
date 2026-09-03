"""AD-2 is enforced by the import-linter contracts in pyproject.toml, not by review.

The forbidden-import case is proved against a throwaway copy of the tree: the real
`src/` is never written to, so the repository stays clean whatever this test does.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = BACKEND_ROOT / "pyproject.toml"

FORBIDDEN_MODULES = (
    "fastapi",
    "sqlalchemy",
    "dbos",
    "subprocess",
    "os",
    "shutil",
    "httpx",
    "langfuse",
    "git",
)


def _lint_imports_executable() -> str | None:
    """Console scripts sit beside the interpreter in a venv, but not on every platform."""
    beside = Path(sys.executable).parent / "lint-imports"
    for candidate in (beside, beside.with_suffix(".exe")):
        if candidate.exists():
            return str(candidate)
    return shutil.which("lint-imports")


LINT_IMPORTS = _lint_imports_executable()

pytestmark = pytest.mark.skipif(LINT_IMPORTS is None, reason="lint-imports not installed")


def _run_lint_imports(project_root: Path) -> subprocess.CompletedProcess[str]:
    assert LINT_IMPORTS is not None
    env = {**os.environ, "PYTHONPATH": str(project_root / "src")}
    return subprocess.run(  # fixed argv, no shell
        [LINT_IMPORTS, "--config", str(project_root / "pyproject.toml"), "--no-cache"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def tree_copy(tmp_path: Path) -> Path:
    """A copy of the backend package that a test may violate freely."""
    root = tmp_path / "backend-api"
    root.mkdir()
    shutil.copytree(BACKEND_ROOT / "src", root / "src")
    shutil.copy(PYPROJECT, root / "pyproject.toml")
    return root


def test_the_real_tree_satisfies_every_contract() -> None:
    result = _run_lint_imports(BACKEND_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr


def test_application_importing_sqlalchemy_breaks_the_forbidden_contract(tree_copy: Path) -> None:
    leak = tree_copy / "src" / "orchestrator" / "application" / "leak.py"
    leak.write_text("import sqlalchemy\n\n\ndef use() -> object:\n    return sqlalchemy\n")

    result = _run_lint_imports(tree_copy)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "AD-2 forbidden: application imports no framework, no I/O" in output
    assert "sqlalchemy" in output
    # the real tree is untouched
    assert not (BACKEND_ROOT / "src" / "orchestrator" / "application" / "leak.py").exists()


def test_domain_importing_a_layer_above_breaks_the_layers_contract(tree_copy: Path) -> None:
    leak = tree_copy / "src" / "orchestrator" / "domain" / "leak.py"
    leak.write_text("from orchestrator.application import __name__ as up\n")

    result = _run_lint_imports(tree_copy)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert "AD-2 layers" in output


def _forbidden_contracts() -> dict[str, list[str]]:
    config = tomllib.loads(PYPROJECT.read_text())
    contracts = config["tool"]["importlinter"]["contracts"]
    return {
        source: contract["forbidden_modules"]
        for contract in contracts
        if contract["type"] == "forbidden"
        for source in contract["source_modules"]
    }


@pytest.mark.parametrize("layer", ["orchestrator.domain", "orchestrator.application"])
@pytest.mark.parametrize("module", FORBIDDEN_MODULES)
def test_every_forbidden_module_is_declared_for_both_inner_layers(layer: str, module: str) -> None:
    declared = _forbidden_contracts()

    assert layer in declared, f"no forbidden contract for {layer}"
    assert module in declared[layer], f"{module} not forbidden for {layer}"


def test_external_packages_are_analysed_or_the_forbidden_contracts_are_inert() -> None:
    """Without this flag import-linter cannot see `sqlalchemy` at all."""
    config = tomllib.loads(PYPROJECT.read_text())

    assert config["tool"]["importlinter"]["include_external_packages"] is True
