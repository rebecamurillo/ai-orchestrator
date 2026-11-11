"""Migration 0032 creates `instance_hold` (story 4, AD-30) — read as an AST, in the pattern of
`test_template_source_migration.py`; `test_migration_chain.py` checks the chain itself."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0032_instance_hold.py"


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


def test_the_revision_follows_template_version_source() -> None:
    assert constant("revision") == "0032_instance_hold"
    assert constant("down_revision") == "0031_template_version_source"


def test_the_upgrade_creates_the_table_with_its_four_columns() -> None:
    source = ast.unparse(function("upgrade"))

    assert "op.create_table('instance_hold'" in source
    assert "sa.Column('id', sa.Uuid(), primary_key=True)" in source
    assert "sa.Column('held_at', sa.DateTime(timezone=True), nullable=False)" in source
    assert "sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False)" in source
    assert "sa.Column('reason', sa.Text(), nullable=False)" in source


def test_the_downgrade_drops_it() -> None:
    assert "op.drop_table('instance_hold')" in ast.unparse(function("downgrade"))
