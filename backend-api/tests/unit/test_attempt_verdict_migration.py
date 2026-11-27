"""Migration 0049 adds the gate verdict columns to `attempt` — read as an AST (epic 8 story 2)."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0049_attempt_verdict.py"


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


def test_the_revision_follows_the_initiative_tables() -> None:
    assert constant("revision") == "0049_attempt_verdict"
    assert constant("down_revision") == "0048_initiative"


def test_the_upgrade_adds_three_nullable_columns() -> None:
    upgrade = source_of("upgrade")

    assert (
        "op.add_column('attempt', sa.Column('verdict_word', sa.Text(), nullable=True))" in upgrade
    )
    assert (
        "op.add_column('attempt', sa.Column('verdict_fields', postgresql.JSONB(), nullable=True))"
        in upgrade
    )
    assert (
        "op.add_column('attempt', sa.Column('verdict_text', sa.Text(), nullable=True))" in upgrade
    )


def test_the_downgrade_drops_all_three() -> None:
    downgrade = source_of("downgrade")

    for name in ("verdict_text", "verdict_fields", "verdict_word"):
        assert f"op.drop_column('attempt', '{name}')" in downgrade
