"""Migration 0033 creates the seven fact tables — read as an AST, as `0032` is."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0033_run_facts.py"
TABLES = (
    "fact_set",
    "gateway_read",
    "usage_fact",
    "request_fact",
    "activity_fact",
    "gap_fact",
    "event_fact",
)


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


def test_the_revision_follows_instance_hold() -> None:
    assert constant("revision") == "0033_run_facts"
    assert constant("down_revision") == "0032_instance_hold"


def test_the_upgrade_creates_the_seven_tables_in_foreign_key_order() -> None:
    source = source_of("upgrade")
    positions = [source.index(f"op.create_table('{name}'") for name in TABLES]
    assert positions == sorted(positions)


def test_the_upgrade_holds_the_database_rules() -> None:
    source = source_of("upgrade")
    assert "(fact_set_id IS NULL) <> (gateway_read_id IS NULL)" in source
    assert "name=op.f('ck_usage_fact_one_parent')" in source
    assert "name='uq_fact_set_attempt_extractor_version'" in source
    assert "'attempt_id', 'extractor', 'extractor_version'" in source
    assert "MONEY = sa.Numeric(12, 6)" in MIGRATION.read_text()
    assert source.count("MONEY") == len(("gateway_read.usd", "usage_fact.usd"))
    assert "sa.Column('class', sa.Text(), nullable=False)" in source
    assert "sa.Column('gaps_s', sa.ARRAY(sa.Integer()), nullable=False)" in source


def test_the_downgrade_drops_all_seven_children_first() -> None:
    tables = next(
        ast.literal_eval(n.value)
        for n in ast.parse(MIGRATION.read_text()).body
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "TABLES"
    )
    assert tables == tuple(reversed(TABLES))
    assert "op.drop_table(table)" in source_of("downgrade")
