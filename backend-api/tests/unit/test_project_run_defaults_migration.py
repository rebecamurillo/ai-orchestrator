"""Migration 0045 adds the five nullable run-default columns to `project` (story 1 of epic 6) —
read as an AST, in the pattern of `test_instance_hold_migration.py`."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0045_project_run_defaults.py"
COLUMNS = (
    "default_budget_usd",
    "default_harness",
    "default_model",
    "default_autonomy",
    "default_senior_model",
)


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
            assert node.value is not None
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def function(name: str) -> ast.FunctionDef:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(name)


def test_the_revision_follows_run_lane() -> None:
    assert constant("revision") == "0045_project_run_defaults"
    assert constant("down_revision") == "0044_run_lane"


def test_the_upgrade_adds_five_nullable_columns() -> None:
    source = ast.unparse(function("upgrade"))

    assert source.count("op.add_column(") == len(COLUMNS)
    assert "'project', sa.Column('default_budget_usd', sa.Numeric(12, 2), nullable=True)" in source
    for name in ("default_harness", "default_model", "default_autonomy", "default_senior_model"):
        assert f"'project', sa.Column('{name}', sa.Text(), nullable=True)" in source


def test_the_downgrade_drops_exactly_those_five() -> None:
    source = ast.unparse(function("downgrade"))

    assert source.count("op.drop_column(") == len(COLUMNS)
    for name in (
        "default_budget_usd",
        "default_harness",
        "default_model",
        "default_autonomy",
        "default_senior_model",
    ):
        assert f"op.drop_column('project', '{name}')" in source
