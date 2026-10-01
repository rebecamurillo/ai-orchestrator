"""AD-4's `/mcp` boundary: the MCP SDK is named in one module, and `make lint` says so.

Written the way `tests/unit/test_dbos_boundary.py` is written, for the reason it gives: a
contract nobody has seen fail might be inert, so the second test writes an `import mcp` into a
throwaway copy of the package and asserts the gate names it.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from tests.unit.test_layering import BACKEND_ROOT, LINT_IMPORTS, PYPROJECT, _run_lint_imports

pytestmark = pytest.mark.skipif(LINT_IMPORTS is None, reason="lint-imports not installed")

#: The one module that may write `import mcp`.
FACADE = "orchestrator.infrastructure.mcp.facade"

#: Where a leak is written in the throwaway tree, and what it says.
LEAK = "import mcp\n\n\ndef use() -> object:\n    return mcp\n"

CONTRACT = "AD-4 forbidden: only infrastructure/mcp/facade.py imports mcp"


@pytest.fixture
def tree_copy(tmp_path: Path) -> Path:
    """A copy of the backend package that a test may violate freely."""
    root = tmp_path / "backend-api"
    root.mkdir()
    shutil.copytree(BACKEND_ROOT / "src", root / "src")
    shutil.copy(PYPROJECT, root / "pyproject.toml")
    return root


def _contract() -> dict[str, object]:
    contracts = tomllib.loads(PYPROJECT.read_text())["tool"]["importlinter"]["contracts"]
    return next(entry for entry in contracts if entry["name"] == CONTRACT)


def test_the_contract_covers_the_whole_package_and_excepts_one_module() -> None:
    contract = _contract()

    assert contract["source_modules"] == ["orchestrator"]
    assert contract["forbidden_modules"] == ["mcp"]
    assert contract["ignore_imports"] == [f"{FACADE} -> mcp"]
    assert contract["allow_indirect_imports"] is True


def test_the_real_tree_keeps_it() -> None:
    result = _run_lint_imports(BACKEND_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_second_import_of_the_sdk_breaks_the_contract(tree_copy: Path) -> None:
    leak = tree_copy / "src" / "orchestrator" / "api" / "leak.py"
    leak.write_text(LEAK)

    result = _run_lint_imports(tree_copy)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert CONTRACT in output
    assert "orchestrator.api.leak -> mcp" in output
    real = BACKEND_ROOT / "src" / "orchestrator" / "api" / "leak.py"
    assert not real.exists()


def test_the_facade_is_the_module_the_exception_names() -> None:
    """A renamed facade must move the exception with it, or the rule stops being checked."""
    module = BACKEND_ROOT / "src" / "orchestrator" / "infrastructure" / "mcp" / "facade.py"

    assert module.is_file()
    assert "from mcp.server" in module.read_text()
