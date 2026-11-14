"""Migration 0034 adds the five `run` spend-figure columns (story 5, owner decision T4,
2026-11-12) — read as an AST, in the pattern of `test_instance_hold_migration.py`."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0034_run_spend_figures.py"
MONEY = ("gateway_spend_usd", "harness_spend_usd", "gate_spend_usd")
FLAGS = ("gateway_reported", "harness_reported")


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        target = node.target if isinstance(node, ast.AnnAssign) else None
        if isinstance(node, ast.Assign):
            target = node.targets[0]
        if getattr(target, "id", None) == name and node.value is not None:  # type: ignore[union-attr]
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def function(name: str) -> ast.FunctionDef:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(name)


def test_the_revision_follows_run_facts() -> None:
    assert constant("revision") == "0034_run_spend_figures"
    assert constant("down_revision") == "0033_run_facts"


def test_the_upgrade_adds_five_not_null_columns_with_server_defaults() -> None:
    source = ast.unparse(function("upgrade"))

    assert constant("MONEY_COLUMNS") == MONEY
    assert constant("FLAG_COLUMNS") == FLAGS
    assert (
        "op.add_column('run', sa.Column(name, MONEY, nullable=False, server_default='0'))" in source
    )
    assert (
        "op.add_column('run', sa.Column(name, sa.Boolean(), nullable=False, "
        "server_default=sa.false()))" in source
    )
    assert "MONEY = sa.Numeric(12, 6)" in ast.unparse(ast.parse(MIGRATION.read_text()))


def test_the_downgrade_drops_them() -> None:
    source = ast.unparse(function("downgrade"))

    assert "op.drop_column('run', name)" in source
    assert "reversed(FLAG_COLUMNS + MONEY_COLUMNS)" in source
