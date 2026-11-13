"""Revision 0038 adds the Run label columns and writes every existing Run's default (story 3)."""

from __future__ import annotations

import ast
import importlib.util
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0038_run_label.py"
AT = datetime(2026, 11, 10, 10, 23, 41, tzinfo=UTC)


def load() -> Any:
    spec = importlib.util.spec_from_file_location("migration_0038", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def function(name: str) -> ast.FunctionDef:
    for node in ast.parse(MIGRATION.read_text()).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(name)


def test_the_revision_follows_run_repository_records() -> None:
    module = load()

    assert module.revision == "0038_run_label"
    assert module.down_revision == "0037_run_repository_records"


def test_both_columns_are_not_null_with_server_defaults() -> None:
    source = ast.unparse(function("upgrade"))

    assert source.count("nullable=False") == len(("label", "label_set_by_operator"))
    assert "server_default=''" in source
    assert "server_default=sa.false()" in source
    assert "'label'" in source and "'label_set_by_operator'" in source


def test_the_downgrade_drops_both_columns() -> None:
    source = ast.unparse(function("downgrade"))

    assert "drop_column('run', 'label_set_by_operator')" in source
    assert "drop_column('run', 'label')" in source


def test_labels_of_gives_every_run_its_default() -> None:
    rows = [
        {
            "id": UUID(int=1),
            "name": "familio",
            "inputs": {"initiative_folder": "initiatives/snake"},
            "template_name": "bench",
            "created_at": AT,
        },
        {
            "id": UUID(int=2),
            "name": None,
            "inputs": None,
            "template_name": "repo-init",
            "created_at": AT,
        },
    ]

    assert load().labels_of(rows) == {
        UUID(int=1): "familio snake bench 2026-11-10 10:23",
        UUID(int=2): "repo-init 2026-11-10 10:23",
    }
