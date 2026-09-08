"""`Workspace.mtime`: the one question AD-13's de-ambiguation archive asks the filesystem.

"Keep the newest match, archive the rest" needs an order over files, and neither `glob` nor
`read` can give one. It is a port method rather than a `Path.stat()` call in the executor
because `application/` reads the worktree through the port and nothing else (AD-2).

The real adapter and the shared fake are asserted side by side, because a use case tested
against a fake that answered differently would pass here and be wrong in the container.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from orchestrator.domain.ports.workspace import Workspace, WorkspaceError
from orchestrator.infrastructure.workspace.fs import FsWorkspace
from tests.unit.fakes.workspace import FakeWorkspace

NEWER = 1_700_000_500.0
OLDER = 1_700_000_100.0


def test_the_port_declares_it_so_both_sides_are_the_same_question() -> None:
    assert hasattr(Workspace, "mtime")


def test_the_real_workspace_reports_the_file_it_was_given(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("a")
    (tmp_path / "b.md").write_text("b")
    os.utime(tmp_path / "a.md", (OLDER, OLDER))
    os.utime(tmp_path / "b.md", (NEWER, NEWER))
    workspace = FsWorkspace(str(tmp_path))

    assert workspace.mtime("b.md") > workspace.mtime("a.md")


def test_the_real_workspace_answers_zero_for_a_path_that_is_not_there(tmp_path: Path) -> None:
    """The caller is choosing a newest among files it globbed; a race that removed one
    must not raise inside a prepare phase that has already committed."""
    assert FsWorkspace(str(tmp_path)).mtime("gone.md") == 0.0


def test_the_real_workspace_refuses_a_path_outside_its_root(tmp_path: Path) -> None:
    with pytest.raises(WorkspaceError):
        FsWorkspace(str(tmp_path)).mtime("../escape.md")


def test_the_real_workspace_with_no_root_refuses_this_call_too() -> None:
    with pytest.raises(WorkspaceError):
        FsWorkspace(None).mtime("a.md")


def test_the_fake_answers_the_times_it_was_given() -> None:
    workspace = FakeWorkspace(
        files={"a.md": "a", "b.md": "b"}, mtimes={"a.md": OLDER, "b.md": NEWER}
    )

    assert workspace.mtime("b.md") > workspace.mtime("a.md")


def test_the_fake_answers_zero_for_a_file_it_holds_no_time_for() -> None:
    assert FakeWorkspace(files={"a.md": "a"}).mtime("a.md") == 0.0


def test_the_fake_refuses_the_same_paths_the_real_one_does() -> None:
    with pytest.raises(WorkspaceError):
        FakeWorkspace().mtime("/absolute.md")
