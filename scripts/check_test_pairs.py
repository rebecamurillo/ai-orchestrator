#!/usr/bin/env python3
"""Prove that every module under a source package has a test module that imports it (AD-18).

`make lint` runs this over `backend-api/src/orchestrator` against `backend-api/tests/unit`.
It fails in one direction only — a source module no unit test imports — and it names the
module, because "add a test" is only actionable when the gate says which file.

**Why it runs on the system interpreter rather than under `uv`.** `backend-api/tests/unit/
test_makefile.py` is frozen and asserts that the `lint` recipe holds exactly as many `uv`
invocations as it has declared sub-gates. A sixth one would fail that anchor, so this script
imports nothing outside the standard library and `make lint` calls it as
`$(PYTHON) scripts/check_test_pairs.py`.

**What counts as a pair.** A module is paired when some module under the unit-test tree
imports it — by `import a.b.c`, by `from a.b import c`, or through a package: importing
`a.b` executes `a/b/__init__.py`, so whatever that file imports is imported too, however
many packages deep the re-export chain runs. Imports made by ordinary source modules are
*not* followed: everything is reachable from `main.py`, and a rule built on that would pass
for a package with no tests at all.

Usage: `python3 scripts/check_test_pairs.py [--src PATH] [--tests PATH]`. Both default to
the backend package; they exist so `tests/unit/test_check_test_pairs.py` can drive the gate
against scratch trees and prove it fires.

Because `python3` is whatever the machine has — 3.9 on a stock macOS — this module stays
inside the standard library and inside syntax that old: no `match`, no runtime `X | Y`.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SRC = REPO_ROOT / "backend-api" / "src" / "orchestrator"
DEFAULT_TESTS = REPO_ROOT / "backend-api" / "tests" / "unit"

#: A package marker holds no behaviour of its own.
PACKAGE_MARKER = "__init__.py"
#: The composition root, whose wiring the e2e stack exercises and a unit test cannot. Only
#: the one at the top of the package: a deeper `main.py` is a module like any other.
COMPOSITION_ROOT = "main.py"


def _display(path: Path) -> str:
    """The path as a reader would type it, relative to the repository when it is inside it."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def dotted_name(module: Path, package_root: Path) -> str:
    """The import path of a file inside a package, e.g. `orchestrator.domain.ids`."""
    relative = module.relative_to(package_root.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def source_modules(package_root: Path) -> dict[str, Path]:
    """Every `*.py` file in the package, by import path."""
    return {dotted_name(path, package_root): path for path in sorted(package_root.rglob("*.py"))}


def is_exempt(module: Path, package_root: Path) -> bool:
    return module.name == PACKAGE_MARKER or module == package_root / COMPOSITION_ROOT


def imported_names(module: Path) -> set[str]:
    """The dotted names one module's import statements refer to.

    `from a.b import c` yields both `a.b` and `a.b.c`: which of the two is a module is a
    question about the source tree, answered by the caller, not by the syntax.

    A module that does not parse is reported as itself rather than as a traceback: the gate
    names the file it could not read, and ruff is what says why.
    """
    names: set[str] = set()
    try:
        tree = ast.parse(module.read_text(), filename=str(module))
    except SyntaxError as error:
        raise SystemExit(
            f"{_display(module)}:{error.lineno}: cannot be parsed: {error.msg}"
        ) from None
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module)
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return names


def paired_modules(package_root: Path, tests_root: Path) -> set[str]:
    """The package modules the test tree imports, following package re-exports.

    A package that is imported has its `__init__.py` executed, so the modules that file
    imports are imported as well; the worklist below is what makes that transitive.
    """
    modules = source_modules(package_root)
    packages = {name for name, path in modules.items() if path.name == "__init__.py"}

    pending: set[str] = set()
    for test_module in sorted(tests_root.rglob("*.py")):
        pending |= imported_names(test_module)

    reached: set[str] = set()
    while pending:
        name = pending.pop()
        if name in reached or name not in modules:
            continue
        reached.add(name)
        if name in packages:
            pending |= imported_names(modules[name])
    return reached


def checked_modules(package_root: Path) -> list[tuple[str, Path]]:
    """The modules the rule applies to, in path order."""
    return sorted(
        (
            (name, path)
            for name, path in source_modules(package_root).items()
            if not is_exempt(path, package_root)
        ),
        key=lambda item: item[1],
    )


def unpaired_modules(package_root: Path, tests_root: Path) -> list[tuple[str, Path]]:
    """The modules with no test module importing them, in path order."""
    reached = paired_modules(package_root, tests_root)
    return [(name, path) for name, path in checked_modules(package_root) if name not in reached]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that every source module has a test.")
    parser.add_argument("--src", type=Path, default=DEFAULT_SRC, help="the source package")
    parser.add_argument("--tests", type=Path, default=DEFAULT_TESTS, help="the unit-test tree")
    args = parser.parse_args(argv)

    for label, directory in (("--src", args.src), ("--tests", args.tests)):
        if not directory.is_dir():
            sys.stderr.write(f"{_display(directory)}: {label} is not a directory\n")
            return 1

    orphans = unpaired_modules(args.src, args.tests)
    tests_label = _display(args.tests)
    for name, path in orphans:
        sys.stderr.write(
            f"{_display(path)}: no module under {tests_label} imports {name} — "
            "every source module has a test module (AD-18)\n"
        )
    if orphans:
        sys.stderr.write(f"test pairs: {len(orphans)} source module(s) without a test module\n")
        return 1

    checked = len(checked_modules(args.src))
    sys.stdout.write(
        f"test pairs: {checked} module{'s' if checked != 1 else ''} under "
        f"{_display(args.src)}, each imported by a module under {tests_label}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
