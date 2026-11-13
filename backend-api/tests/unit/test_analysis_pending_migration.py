"""Migration 0042: an analysis may exist before its calculation, read as an AST (epic 5 s4)."""

from __future__ import annotations

import ast

import orchestrator.infrastructure.db.models  # noqa: F401 — registers every table
from orchestrator.infrastructure.db.base import Base
from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0042_analysis_pending.py"


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


def test_the_revision_follows_the_analysis_tables() -> None:
    assert constant("revision") == "0042_analysis_pending"
    assert constant("down_revision") == "0041_analysis"


def test_the_upgrade_frees_the_calculation_and_adds_the_analysis_ids() -> None:
    upgrade = source_of("upgrade")
    assert "op.alter_column('analysis', 'calculation_id'" in upgrade
    assert "nullable=True" in upgrade
    assert "op.add_column('result_version'" in upgrade
    assert "sa.Column('analysis_ids', JSONB()" in upgrade
    assert "nullable=False" in upgrade
    assert "server_default=sa.text(\"'[]'::jsonb\")" in upgrade


def test_the_model_carries_the_same_database_default_as_the_migration() -> None:
    column = Base.metadata.tables["result_version"].columns["analysis_ids"]
    assert not column.nullable
    assert column.server_default is not None
    assert "'[]'::jsonb" in str(column.server_default.arg)  # type: ignore[attr-defined]


def test_the_downgrade_deletes_pending_rows_before_restoring_the_constraint() -> None:
    downgrade = source_of("downgrade")
    assert downgrade.index("analysis_artifact") < downgrade.index("DELETE FROM analysis WHERE")
    assert downgrade.index("DELETE FROM analysis WHERE") < downgrade.index("nullable=False")
    assert "op.drop_column('result_version', 'analysis_ids')" in downgrade
