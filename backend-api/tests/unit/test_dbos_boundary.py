"""AD-6's own boundary: `dbos` is named in one module, and `make lint` is what says so.

`tests/unit/test_layering.py` proves the AD-2 contracts the same way and is frozen, so this
module is the AD-6 half rather than an edit to that one. It borrows that module's runner, so
both read `pyproject.toml` and invoke `lint-imports` identically.

The second test is the one that matters: a contract nobody has seen fail is a contract that
might be inert. It writes an `import dbos` into a throwaway copy of the package and asserts
the gate names it.
"""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

import pytest

from tests.unit.test_layering import BACKEND_ROOT, LINT_IMPORTS, PYPROJECT, _run_lint_imports

pytestmark = pytest.mark.skipif(LINT_IMPORTS is None, reason="lint-imports not installed")

#: The one module that may write `import dbos` (AD-6).
FACADE = "orchestrator.infrastructure.dbos.facade"

#: Where a leak is written in the throwaway tree, and what it says.
LEAK = "import dbos\n\n\ndef use() -> object:\n    return dbos\n"

CONTRACT = "AD-6 forbidden: only infrastructure/dbos/facade.py imports dbos"


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
    assert contract["forbidden_modules"] == ["dbos"]
    assert contract["ignore_imports"] == [f"{FACADE} -> dbos"]


def test_the_contract_is_about_who_writes_the_import_not_who_is_reachable() -> None:
    """`main.py` wires the adapter; the rule is which module names the library."""
    assert _contract()["allow_indirect_imports"] is True


def test_the_real_tree_keeps_it() -> None:
    result = _run_lint_imports(BACKEND_ROOT)

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_second_import_of_the_library_breaks_the_contract(tree_copy: Path) -> None:
    leak = tree_copy / "src" / "orchestrator" / "infrastructure" / "db" / "leak.py"
    leak.write_text(LEAK)

    result = _run_lint_imports(tree_copy)
    output = result.stdout + result.stderr

    assert result.returncode != 0, output
    assert CONTRACT in output
    assert "orchestrator.infrastructure.db.leak -> dbos" in output
    real = BACKEND_ROOT / "src" / "orchestrator" / "infrastructure" / "db" / "leak.py"
    assert not real.exists()


def test_the_facade_is_the_module_the_exception_names() -> None:
    """A renamed facade must move the exception with it, or the rule stops being checked."""
    module = BACKEND_ROOT / "src" / "orchestrator" / "infrastructure" / "dbos" / "facade.py"

    assert module.is_file()
    assert "from dbos import" in module.read_text()
