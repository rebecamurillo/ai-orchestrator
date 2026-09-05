"""The revision the process reports is the end of one unbroken chain rooted at the baseline.

`tests/unit/test_migrations.py` asserts what the head *is* by asking Alembic
(`ScriptDirectory.get_heads()`). That answer moves with every story that adds a revision,
which is the point — but it means the assertion cannot also prove the tree behind the head
is sound: a second root, an orphan file, or a fork would still report a head.

This module closes that from the other side, and without Alembic's revision map: the
committed `alembic/versions/*.py` files are read as source, their `revision` and
`down_revision` values collected, and the chain walked forward from `BASELINE_REVISION`.
Every committed file must appear in that walk exactly once, and the revision `run_migrations`
returns and logs must be the walk's last element.

Written when story 2.1 needed `0002_project` and found two assertions in the anchor module
pinned to the literal baseline. Those two were narrowed to the tree head; this module covers
what they stopped covering — that the reported head is the terminal of the committed chain,
and that the chain starts where the baseline says it does — for every revision count, not
only for one.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from orchestrator.infrastructure.db import migrations
from orchestrator.infrastructure.db.migrations import (
    BASELINE_REVISION,
    alembic_config,
    head_revision,
    run_migrations,
)
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings
from tests.unit.conftest import REPO_ROOT

VERSIONS = REPO_ROOT / "backend-api" / "alembic" / "versions"


def _revision_ids(path: Path) -> tuple[str, str | None]:
    """`(revision, down_revision)` read from the file's own assignments, not from Alembic."""
    values: dict[str, Any] = {}
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id in {"revision", "down_revision"}:
            assert value is not None, f"{path.name} declares {target.id} without a value"
            values[target.id] = ast.literal_eval(value)

    assert "revision" in values, f"{path.name} declares no revision id"
    return values["revision"], values.get("down_revision")


def _committed_parents() -> dict[str, str | None]:
    paths = sorted(VERSIONS.glob("*.py"))
    assert paths, f"no revision files under {VERSIONS}"
    return dict(_revision_ids(path) for path in paths)


def _chain() -> list[str]:
    """The revisions in application order, walked forward from the baseline."""
    parents = _committed_parents()
    children = {down: revision for revision, down in parents.items()}
    order = [BASELINE_REVISION]
    while order[-1] in children:
        order.append(children[order[-1]])
    return order


def test_the_baseline_is_the_only_revision_without_a_parent() -> None:
    parents = _committed_parents()

    roots = [revision for revision, down in parents.items() if down is None]

    assert roots == [BASELINE_REVISION]


def test_every_committed_revision_hangs_in_one_line_from_the_baseline() -> None:
    """A fork or an orphan would leave a file out of the walk; a merge would repeat one."""
    parents = _committed_parents()

    order = _chain()

    assert len(order) == len(parents), f"walked {order}, but {sorted(parents)} are committed"
    assert set(order) == set(parents)


def test_the_head_alembic_reports_is_the_end_of_that_chain(env: dict[str, str]) -> None:
    assert head_revision(alembic_config(Settings())) == _chain()[-1]


def test_run_migrations_returns_the_end_of_that_chain(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(migrations.command, "upgrade", lambda config, revision: None)

    assert run_migrations(Settings()) == _chain()[-1]


def test_the_applied_line_names_the_end_of_that_chain(
    env: dict[str, str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The operator reads this line to know which revision the schema is at."""
    monkeypatch.setattr(migrations.command, "upgrade", lambda config, revision: None)
    configure_logging("info")

    run_migrations(Settings())

    out = capsys.readouterr().out
    assert "migrations applied" in out
    assert _chain()[-1] in out
