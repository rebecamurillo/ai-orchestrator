"""Migration 0047 adds `project_package` and `template_version.package_sha` (story 3 of epic 6)."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

COLUMNS = 9
MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0047_project_package.py"


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


def test_the_revision_follows_the_initiative_folder() -> None:
    assert constant("revision") == "0047_project_package"
    assert constant("down_revision") == "0046_repository_initiative_folder"


def test_the_upgrade_creates_the_table_with_every_column_not_null() -> None:
    source = ast.unparse(function("upgrade"))

    assert source.count("op.create_table(") == 1
    for column in ("id", "project_id", "repository_id", "path", "ref", "sha", "name"):
        assert f"sa.Column('{column}', sa.Uuid(), nullable=False)" in source or (
            f"sa.Column('{column}', sa.Text(), nullable=False)" in source
        )
    assert (
        "sa.Column('declaration', postgresql.JSONB(astext_type=sa.Text()), nullable=False)"
        in source
    )
    assert "sa.Column('installed_at', sa.DateTime(timezone=True), nullable=False)" in source
    assert source.count("nullable=False") == COLUMNS
    assert "sa.UniqueConstraint('project_id'" in source
    assert "['project_id'], ['project.id']" in source
    assert "['repository_id'], ['repository.id']" in source


def test_the_upgrade_adds_the_nullable_package_sha() -> None:
    source = ast.unparse(function("upgrade"))

    assert source.count("op.add_column(") == 1
    assert (
        "op.add_column('template_version', sa.Column('package_sha', sa.Text(), nullable=True))"
        in source
    )


def test_the_downgrade_drops_exactly_these() -> None:
    source = ast.unparse(function("downgrade"))

    assert source.count("op.drop_column(") == 1
    assert source.count("op.drop_table(") == 1
    assert "op.drop_column('template_version', 'package_sha')" in source
    assert "op.drop_table('project_package')" in source
