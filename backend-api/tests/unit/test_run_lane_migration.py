"""Migration 0044: `run.lane`, read as an AST (epic 3 story 2, AC8)."""

from __future__ import annotations

import ast

import orchestrator.infrastructure.db.models  # noqa: F401 — registers every table
from orchestrator.infrastructure.db.base import Base
from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0044_run_lane.py"


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


def test_the_revision_follows_attempt_log_removed() -> None:
    assert constant("revision") == "0044_run_lane"
    assert constant("down_revision") == "0043_attempt_log_removed"


def test_the_upgrade_adds_a_not_null_text_column_defaulting_to_walk() -> None:
    upgrade = source_of("upgrade")
    assert "op.add_column('run'" in upgrade
    assert "sa.Column('lane', sa.Text()" in upgrade
    assert "nullable=False" in upgrade
    assert "server_default=sa.text(\"'walk'\")" in upgrade


def test_the_downgrade_drops_the_column() -> None:
    assert "op.drop_column('run', 'lane')" in source_of("downgrade")


def test_the_model_column_is_not_nullable_and_has_a_server_default() -> None:
    column = Base.metadata.tables["run"].columns["lane"]
    assert not column.nullable
    assert column.server_default is not None
