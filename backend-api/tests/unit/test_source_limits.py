"""The limits `backend-api/AGENTS.md` calls checkable, actually checked.

ruff covers complexity and statement counts; module length and the `Clock` rule have no
rule behind them, so they are asserted here rather than left as prose.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "orchestrator"
MAX_MODULE_LINES = 400

MODULES = sorted(SRC.rglob("*.py"))
# `Clock` exists so that time is injected; only adapters may read the wall clock.
LAYERS_WITHOUT_WALL_CLOCK = ("domain", "application", "api")


def test_the_package_has_modules_to_check() -> None:
    assert MODULES


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_a_module_is_at_most_400_lines(module: Path) -> None:
    lines = len(module.read_text().splitlines())

    assert lines <= MAX_MODULE_LINES, f"{module.name}: {lines} lines"


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_module_calls_print(module: Path) -> None:
    tree = ast.parse(module.read_text())

    calls = [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    assert "print" not in calls, f"{module.name}: log with structlog instead"


@pytest.mark.parametrize(
    "module",
    [m for m in MODULES if any(layer in m.parts for layer in LAYERS_WITHOUT_WALL_CLOCK)],
    ids=lambda p: p.name,
)
def test_only_infrastructure_reads_the_wall_clock(module: Path) -> None:
    tree = ast.parse(module.read_text())

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in ("now", "utcnow", "today"):
            target = node.func.value
            name = target.id if isinstance(target, ast.Name) else None
            assert name != "datetime", f"{module.name}: take a Clock port instead"
