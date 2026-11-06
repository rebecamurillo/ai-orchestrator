"""Migration 0031 adds `template_version.source` (story 4, AD-26) — read as an AST, in the
pattern of `test_consult_migration.py`; `test_migration_chain.py` checks the chain itself."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0031_template_version_source.py"


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


def test_the_revision_follows_chat_thread_close() -> None:
    assert constant("revision") == "0031_template_version_source"
    assert constant("down_revision") == "0030_chat_thread_close"


def test_the_upgrade_adds_one_nullable_source_column() -> None:
    source = ast.unparse(function("upgrade"))

    assert "op.add_column('template_version'" in source
    assert "sa.Column('source', sa.Text(), nullable=True)" in source


def test_the_downgrade_drops_it() -> None:
    assert "op.drop_column('template_version', 'source')" in ast.unparse(function("downgrade"))
