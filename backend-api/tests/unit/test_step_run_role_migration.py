"""Migration 0036 adds `step_run.role` — read as an AST, as `0033` is."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0036_step_run_role.py"


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
            assert node.value is not None
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def source_of(name: str) -> str:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(name)


def test_the_revision_follows_migrated_attempt_facts() -> None:
    assert constant("revision") == "0036_step_run_role"
    assert constant("down_revision") == "0035_migrated_attempt_facts"


def test_the_upgrade_adds_a_not_null_text_column_defaulting_to_empty() -> None:
    assert source_of("upgrade") == (
        "def upgrade() -> None:\n"
        "    op.add_column('step_run', "
        "sa.Column('role', sa.Text(), nullable=False, server_default=''))"
    )


def test_the_downgrade_drops_it() -> None:
    assert "op.drop_column('step_run', 'role')" in source_of("downgrade")
