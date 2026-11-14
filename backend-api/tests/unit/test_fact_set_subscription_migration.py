"""Revision 0040 adds the nullable `fact_set.subscription` and writes nothing (epic 4 story 1)."""

from __future__ import annotations

import ast
import importlib.util
from typing import Any

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0040_fact_set_subscription.py"


def load() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0040", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function(name: str) -> ast.FunctionDef:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(name)


def test_the_revision_follows_the_metric_results() -> None:
    module = load()

    assert module.revision == "0040_fact_set_subscription"
    assert module.down_revision == "0039_metric_results"


def test_the_column_is_a_nullable_boolean_with_no_default_and_no_data_written() -> None:
    source = ast.unparse(function("upgrade"))

    assert "add_column('fact_set'" in source
    assert "'subscription'" in source and "sa.Boolean()" in source
    assert "nullable=True" in source
    assert "server_default" not in source
    for write in ("execute", "UPDATE", "INSERT", "bulk_insert"):
        assert write not in source


def test_the_downgrade_drops_the_column() -> None:
    assert "drop_column('fact_set', 'subscription')" in ast.unparse(function("downgrade"))
