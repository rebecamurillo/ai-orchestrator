"""Migration 0043: `attempt.log_removed_at`, read as an AST (epic 1 story 3, AD-40)."""

from __future__ import annotations

import ast

import orchestrator.infrastructure.db.models  # noqa: F401 — registers every table
from orchestrator.infrastructure.db.base import Base
from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0043_attempt_log_removed.py"


def constant(name: str) -> object:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.AnnAssign | ast.Assign):
            target = node.target if isinstance(node, ast.AnnAssign) else node.targets[0]
            if getattr(target, "id", None) == name:
                assert node.value is not None
                return ast.literal_eval(node.value)
    raise AssertionError(name)


def source_of(name: str) -> str:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.unparse(node)
    raise AssertionError(name)


def test_the_revision_follows_analysis_pending() -> None:
    assert constant("revision") == "0043_attempt_log_removed"
    assert constant("down_revision") == "0042_analysis_pending"


def test_the_upgrade_adds_a_nullable_timestamptz() -> None:
    upgrade = source_of("upgrade")
    assert "op.add_column('attempt'" in upgrade
    assert "sa.Column('log_removed_at', sa.DateTime(timezone=True)" in upgrade
    assert "nullable=True" in upgrade


def test_the_downgrade_drops_the_column() -> None:
    assert "op.drop_column('attempt', 'log_removed_at')" in source_of("downgrade")


def test_the_model_column_is_nullable_and_timezone_aware() -> None:
    column = Base.metadata.tables["attempt"].columns["log_removed_at"]
    assert column.nullable
    assert column.type.timezone  # type: ignore[attr-defined]
