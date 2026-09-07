"""`FsWorkspace.remove` (SPEC CAP-11, AD-14): the one write `worktree_gc` needs that
`tests/unit/test_fs_workspace.py` predates. A file, a directory (recursively), and a path
already gone — the same "already gone is not a failure" convention `Git.remove_worktree`
and `Git.delete_branch` already state (`domain/ports/git.py`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.workspace import WorkspaceError
from orchestrator.infrastructure.workspace.fs import FsWorkspace


def test_removing_a_file_deletes_it(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("a.txt", "hello")

    workspace.remove("a.txt")

    assert not (tmp_path / "a.txt").exists()


def test_removing_a_directory_deletes_it_recursively(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("run-id/001-1.log", "log line")
    workspace.write("run-id/nested/002-1.log", "another")

    workspace.remove("run-id")

    assert not (tmp_path / "run-id").exists()


def test_removing_a_path_already_gone_is_not_a_failure(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    workspace.remove("never-existed")


def test_removing_leaves_a_sibling_untouched(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("keep.txt", "keep")
    workspace.write("gone.txt", "gone")

    workspace.remove("gone.txt")

    assert workspace.read("keep.txt") == "keep"


def test_removing_outside_the_root_is_refused(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    with pytest.raises(WorkspaceError):
        workspace.remove("../secret")


def test_a_workspace_with_no_root_refuses_remove() -> None:
    workspace = FsWorkspace(None)

    with pytest.raises(WorkspaceError):
        workspace.remove("anything")
