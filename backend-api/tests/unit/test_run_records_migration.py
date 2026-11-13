"""Migration 0037 adds `run_repository` and `run_commit` — read as an AST, as `0033` is."""

from __future__ import annotations

import ast

from tests.unit.conftest import REPO_ROOT

MIGRATION = REPO_ROOT / "backend-api" / "alembic" / "versions" / "0037_run_repository_records.py"


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


def test_the_revision_follows_step_run_role() -> None:
    assert constant("revision") == "0037_run_repository_records"
    assert constant("down_revision") == "0036_step_run_role"


def test_run_repository_columns_and_unique_key() -> None:
    upgrade = source_of("upgrade")
    assert "op.create_table('run_repository'" in upgrade
    for column in ("path", "remote_url", "base_branch", "branch", "base_tip"):
        assert f"sa.Column('{column}', sa.Text(), nullable=False)" in upgrade
    for column in ("head_pushed", "head_local_at_end"):
        assert f"sa.Column('{column}', sa.Text(), nullable=True)" in upgrade
    assert "name='uq_run_repository_run_path'" in upgrade
    assert "sa.UniqueConstraint('run_id', 'path'" in upgrade


def test_run_commit_columns_unique_key_and_made_by_check() -> None:
    upgrade = source_of("upgrade")
    assert "op.create_table('run_commit'" in upgrade
    for column in ("path", "sha", "made_by"):
        assert f"sa.Column('{column}', sa.Text(), nullable=False)" in upgrade
    assert "sa.Column('at', sa.DateTime(timezone=True), nullable=False)" in upgrade
    assert "name='uq_run_commit_run_path_sha'" in upgrade
    assert "sa.UniqueConstraint('run_id', 'path', 'sha'" in upgrade
    assert "name=op.f('ck_run_commit_made_by')" in upgrade
    for token in ("wip", "prepare", "git.commit", "git.merge", "session", "operator_edit"):
        assert f"'{token}'" in upgrade


def test_the_downgrade_drops_both() -> None:
    downgrade = source_of("downgrade")
    assert "op.drop_table('run_commit')" in downgrade
    assert "op.drop_table('run_repository')" in downgrade
