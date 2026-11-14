"""Migration 0041 adds `analysis` and `analysis_artifact` — read as an AST (story 5.1, AC15)."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0041_analysis.py"


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


def test_the_revision_follows_the_fact_set_subscription() -> None:
    assert constant("revision") == "0041_analysis"
    assert constant("down_revision") == "0040_fact_set_subscription"


def test_both_tables_are_created_with_their_columns() -> None:
    upgrade = source_of("upgrade")
    assert constant("ANALYSIS_TABLE") == "analysis"
    assert constant("ARTIFACT_TABLE") == "analysis_artifact"
    assert "op.create_table(ANALYSIS_TABLE" in upgrade
    assert "op.create_table(ARTIFACT_TABLE" in upgrade
    for column in (
        "run_id",
        "calculation_id",
        "repository_path",
        "base",
        "head",
        "toolset",
        "toolset_fingerprint",
        "declaration_hash",
        "status",
        "output",
        "created_at",
        "analysis_id",
        "tool",
        "media_type",
        "body",
    ):
        assert f"sa.Column('{column}'" in upgrade
    assert "sa.LargeBinary()" in upgrade
    assert "sa.ForeignKey('run.id')" in upgrade
    assert "sa.ForeignKey('metric_calculation.id')" in upgrade


def test_the_status_is_checked() -> None:
    assert constant("STATUSES") == "status IN ('ok', 'partial', 'failed')"
    assert "sa.CheckConstraint(STATUSES" in source_of("upgrade")


def test_the_downgrade_drops_the_artifact_then_the_analysis() -> None:
    downgrade = source_of("downgrade")
    assert downgrade.index("ARTIFACT_TABLE") < downgrade.index("ANALYSIS_TABLE")
    assert "op.drop_table" in downgrade
