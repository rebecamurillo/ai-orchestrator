"""Migration 0048 creates the initiative tables and the run keys (AD-36), read as an AST."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0048_initiative.py"


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", None) == name:
            assert node.value is not None
            return ast.literal_eval(node.value)
    raise AssertionError(name)


def function(name: str) -> str:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(name)


def test_the_revision_follows_project_package() -> None:
    assert constant("revision") == "0048_initiative"
    assert constant("down_revision") == "0047_project_package"


def test_the_upgrade_creates_both_tables_and_the_run_keys() -> None:
    source = function("upgrade")

    for fragment in (
        "op.create_table('initiative'",
        "op.create_table('initiative_advance'",
        "op.add_column('run', sa.Column('initiative_id'",
        "op.add_column('run', sa.Column('initiative_round'",
        "op.add_column('run', sa.Column('initiative_position'",
        "fk_run_initiative_id_initiative",
        "ck_run_initiative_keys_together",
        "'uq_initiative_repository_slug_open'",
        "'uq_run_initiative_key'",
        "postgresql_where=sa.text('cancelled_at IS NULL')",
        "postgresql_where=sa.text('initiative_id IS NOT NULL')",
    ):
        assert fragment in source, fragment
    assert source.index("op.create_table('initiative'") < source.index(
        "op.create_table('initiative_advance'"
    )


def test_the_downgrade_drops_them_in_reverse() -> None:
    source = function("downgrade")

    order = [
        "op.drop_table('initiative_advance')",
        "op.drop_index('uq_run_initiative_key'",
        "ck_run_initiative_keys_together",
        "fk_run_initiative_id_initiative",
        "op.drop_column('run', 'initiative_position')",
        "op.drop_column('run', 'initiative_id')",
        "op.drop_index('uq_initiative_repository_slug_open'",
        "op.drop_table('initiative')",
    ]
    positions = [source.index(item) for item in order]
    assert positions == sorted(positions)
