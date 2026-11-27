"""Migration 0046 adds `repository.initiative_folder` (story 2 of epic 6), read as an AST."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = (
    REPO_ROOT / "backend-api" / "alembic" / "versions" / "0046_repository_initiative_folder.py"
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


def test_the_revision_follows_project_run_defaults() -> None:
    assert constant("revision") == "0046_repository_init_folder"
    assert constant("down_revision") == "0045_project_run_defaults"


def test_the_upgrade_adds_one_not_null_column_defaulting_to_initiatives() -> None:
    source = ast.unparse(function("upgrade"))

    assert source.count("op.add_column(") == 1
    assert (
        "'repository', sa.Column('initiative_folder', sa.Text(), nullable=False, "
        "server_default='initiatives')" in source
    )


def test_the_downgrade_drops_exactly_that_column() -> None:
    source = ast.unparse(function("downgrade"))

    assert source.count("op.drop_column(") == 1
    assert "op.drop_column('repository', 'initiative_folder')" in source
