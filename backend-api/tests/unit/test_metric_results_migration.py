"""Migration 0039 adds the calculation, version and value tables — read as an AST."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0039_metric_results.py"


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


def test_the_revision_follows_the_run_label() -> None:
    assert constant("revision") == "0039_metric_results"
    assert constant("down_revision") == "0038_run_label"


def test_the_three_tables_are_created() -> None:
    upgrade = source_of("upgrade")
    for table in ("CALCULATION_TABLE", "VERSION_TABLE", "VALUE_TABLE"):
        assert f"op.create_table({table}" in upgrade
    assert constant("CALCULATION_TABLE") == "metric_calculation"
    assert constant("VERSION_TABLE") == "result_version"
    assert constant("VALUE_TABLE") == "metric_value"


def test_a_run_has_one_version_per_number() -> None:
    assert "sa.UniqueConstraint('run_id', 'n', name=VERSION_UNIQUE)" in source_of("upgrade")
    assert constant("VERSION_UNIQUE") == "uq_result_version_run_n"


def test_a_value_holds_a_figure_or_a_word_except_partial() -> None:
    assert constant("FIGURE_OR_WORD") == (
        "value_num IS NULL OR missing IS NULL OR missing = 'partial'"
    )
    assert "name=op.f(FIGURE_OR_WORD_CHECK)" in source_of("upgrade")
    assert constant("FIGURE_OR_WORD_CHECK") == "ck_metric_value_figure_or_word"


def test_every_origin_field_has_a_reason_column() -> None:
    assert constant("ORIGIN_TEXT") == (
        "harness",
        "origin_model",
        "origin_repository",
        "branch",
        "commit",
        "base_commit",
    )
    upgrade = source_of("upgrade")
    assert "sa.Column(f'{name}_na', sa.Text(), nullable=True)" in upgrade


def test_every_defaultable_not_null_column_has_a_server_default() -> None:
    tree = ast.parse(MIGRATION.read_text())
    bare: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and ast.unparse(node.func) == "sa.Column"
            and any(k.arg == "nullable" and ast.unparse(k.value) == "False" for k in node.keywords)
            and not any(k.arg == "server_default" for k in node.keywords)
        ):
            bare.append(ast.literal_eval(node.args[0]))
    # foreign keys and the origin ids have no honest default
    assert set(bare) == {"run_id", "version_id", "project_id"}


def test_the_state_is_one_of_four_and_the_run_state_pair_is_indexed() -> None:
    assert constant("STATES") == "state IN ('queued', 'running', 'failed', 'done')"
    upgrade = source_of("upgrade")
    assert "'ix_metric_calculation_run_state'" in upgrade
    assert "'ix_metric_value_version'" in upgrade


def test_the_downgrade_drops_all_three() -> None:
    downgrade = source_of("downgrade")
    for table in ("VALUE_TABLE", "VERSION_TABLE", "CALCULATION_TABLE"):
        assert f"op.drop_table({table})" in downgrade
