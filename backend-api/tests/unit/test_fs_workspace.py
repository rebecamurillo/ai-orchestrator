"""`FsWorkspace`: the `Workspace` port over the real filesystem, rooted at one worktree.

Every path here is relative and every one of them is checked before a file is touched
(AD-14). The acceptance criterion is the traversal one — `read("../secret")` and
`read("/etc/passwd")` both raise — and the rest of this module proves the same rule holds
for every other method, plus the two facts the executors of this epic will actually lean
on: a Workspace with no root refuses everything, and `write` makes whatever directory a
path needs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.domain.ports.workspace import Workspace, WorkspaceError
from orchestrator.infrastructure.workspace.fs import FsWorkspace


def test_the_adapter_satisfies_the_port(tmp_path: Path) -> None:
    workspace: Workspace = FsWorkspace(str(tmp_path))

    assert isinstance(workspace, Workspace)


def test_write_then_read_answers_the_same_text(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    workspace.write("a.txt", "hello")

    assert workspace.read("a.txt") == "hello"


def test_write_creates_the_directories_a_path_needs(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    workspace.write("nested/dir/a.txt", "hello")

    assert (tmp_path / "nested" / "dir" / "a.txt").read_text() == "hello"


def test_reading_a_file_that_is_not_there_answers_nothing(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    assert workspace.read("missing.txt") is None


def test_exists_is_true_for_a_file_and_false_for_nothing(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("a.txt", "hello")

    assert workspace.exists("a.txt") is True
    assert workspace.exists("missing.txt") is False


def test_glob_answers_every_matching_path_relative_to_the_root(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("stories/1.md", "one")
    workspace.write("stories/2.md", "two")
    workspace.write("stories/notes.txt", "not this one")

    assert workspace.glob("stories/*.md") == ("stories/1.md", "stories/2.md")


def test_move_renames_a_file_within_the_root(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("a.txt", "hello")

    workspace.move("a.txt", "b.txt")

    assert workspace.read("a.txt") is None
    assert workspace.read("b.txt") == "hello"


def test_tree_lists_every_file_and_directory_under_a_prefix(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("stories/1.md", "one")
    workspace.write("stories/2.md", "two")

    entries = {entry.path: entry.is_dir for entry in workspace.tree("stories")}

    assert entries == {"stories/1.md": False, "stories/2.md": False}


def test_tree_with_no_prefix_walks_the_whole_root(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))
    workspace.write("a.txt", "hello")

    paths = {entry.path for entry in workspace.tree()}

    assert "a.txt" in paths


def test_tree_of_a_prefix_that_does_not_exist_answers_nothing(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    assert workspace.tree("nope") == ()


@pytest.mark.parametrize("path", ["../secret", "/etc/passwd"])
def test_a_path_that_escapes_the_root_raises(tmp_path: Path, path: str) -> None:
    workspace = FsWorkspace(str(tmp_path))

    with pytest.raises(WorkspaceError):
        workspace.read(path)


def test_every_method_rejects_a_path_that_escapes_the_root(tmp_path: Path) -> None:
    workspace = FsWorkspace(str(tmp_path))

    with pytest.raises(WorkspaceError):
        workspace.write("../secret", "x")
    with pytest.raises(WorkspaceError):
        workspace.exists("../secret")
    with pytest.raises(WorkspaceError):
        workspace.glob("../*")
    with pytest.raises(WorkspaceError):
        workspace.move("../secret", "a.txt")
    with pytest.raises(WorkspaceError):
        workspace.move("a.txt", "../secret")
    with pytest.raises(WorkspaceError):
        workspace.tree("../")


def test_a_workspace_with_no_root_refuses_every_call() -> None:
    """`plan.check` runs before `git.worktree`: `run.worktree_path` is `None` (AD-14)."""
    workspace = FsWorkspace(None)

    with pytest.raises(WorkspaceError):
        workspace.read("a.txt")
    with pytest.raises(WorkspaceError):
        workspace.write("a.txt", "x")
    with pytest.raises(WorkspaceError):
        workspace.exists("a.txt")
    with pytest.raises(WorkspaceError):
        workspace.glob("*")
    with pytest.raises(WorkspaceError):
        workspace.move("a.txt", "b.txt")
    with pytest.raises(WorkspaceError):
        workspace.tree()
