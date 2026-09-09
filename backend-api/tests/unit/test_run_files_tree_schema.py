"""`RunFileEntryOut.of`/`RunFilesTreeOut.of` (story 6-3) — the wire projection of a
`TreeEntry`/`RunFilesTree`. The router tests prove the same shape over a real request; this
is the direct, unit-level counterpart AD-18 asks every source module to have.
"""

from __future__ import annotations

from orchestrator.api.schemas.run_files import RunFileEntryOut, RunFilesTreeOut
from orchestrator.application.use_cases.run_files import RunFilesTree
from orchestrator.domain.ports.workspace import TreeEntry


def test_of_projects_a_file_entry() -> None:
    entry = TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=42, mtime=123.5)

    out = RunFileEntryOut.of(entry)

    assert out.model_dump() == {
        "path": "specs/gates/SPEC.md",
        "kind": "file",
        "size": 42,
        "mtime": 123.5,
    }


def test_of_projects_a_directory_entry_with_zeroed_size_and_mtime() -> None:
    entry = TreeEntry(path="specs/gates/stories", is_dir=True)

    out = RunFileEntryOut.of(entry)

    assert out.model_dump() == {
        "path": "specs/gates/stories",
        "kind": "dir",
        "size": 0,
        "mtime": 0.0,
    }


def test_tree_of_projects_root_and_every_entry() -> None:
    tree = RunFilesTree(
        root="specs/gates",
        entries=(
            TreeEntry(path="specs/gates/SPEC.md", is_dir=False, size=1, mtime=1.0),
            TreeEntry(path="specs/gates/stories", is_dir=True),
        ),
    )

    out = RunFilesTreeOut.of(tree)

    assert out.root == "specs/gates"
    assert [entry.model_dump() for entry in out.entries] == [
        {"path": "specs/gates/SPEC.md", "kind": "file", "size": 1, "mtime": 1.0},
        {"path": "specs/gates/stories", "kind": "dir", "size": 0, "mtime": 0.0},
    ]
