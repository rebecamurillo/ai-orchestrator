"""`list_files_tree` (story 6-3, SPEC CAP-2, FR-19): `GET /runs/{id}/files` with no `path` —
every entry under the Run's own scope folder, recursively. No write capability needed, so
this reuses `read_run_file`'s own `RunFilesPorts` unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from orchestrator.application.use_cases.run_files import RunFilesPorts, list_files_tree
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.workspace import TreeEntry
from tests.unit.fakes.runs import FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

SPEC_FOLDER = "specs/gates"
SPEC_FILE = f"{SPEC_FOLDER}/SPEC.md"
STORIES_FILE = f"{SPEC_FOLDER}/stories.yaml"
STORY_FILE = f"{SPEC_FOLDER}/stories/2-record-the-plan.md"


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "epic",
        "template_version": 1,
        "status": "needs_you",
        "budget_usd": Decimal("10"),
        "inputs": {"spec_folder": SPEC_FOLDER},
        "worktree_path": "/work/acme/widgets/wt/gates",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def ports_for(
    run: Run, files: dict[str, str], mtimes: dict[str, float] | None = None
) -> RunFilesPorts:
    return RunFilesPorts(
        runs=FakeRunRepository([run]),
        workspace=lambda root: FakeWorkspace(root, files=files, mtimes=mtimes),
    )


def test_the_tree_root_is_the_runs_own_scope_folder() -> None:
    run = a_run()
    ports = ports_for(run, {SPEC_FILE: "spec", STORY_FILE: "story"})

    tree = list_files_tree(ports, run.id)

    assert tree.root == SPEC_FOLDER


def test_every_file_under_the_scope_folder_is_a_row_with_size_and_mtime() -> None:
    run = a_run()
    ports = ports_for(run, {SPEC_FILE: "spec text"}, mtimes={SPEC_FILE: 123.5})

    tree = list_files_tree(ports, run.id)

    expected = TreeEntry(path=SPEC_FILE, is_dir=False, size=len("spec text"), mtime=123.5)
    assert expected in tree.entries


def test_a_directory_ancestor_is_its_own_row() -> None:
    run = a_run()
    ports = ports_for(run, {STORY_FILE: "story"})

    tree = list_files_tree(ports, run.id)

    directories = [entry for entry in tree.entries if entry.is_dir]
    assert TreeEntry(path=f"{SPEC_FOLDER}/stories", is_dir=True) in directories


def test_a_file_outside_the_scope_folder_is_not_in_the_tree() -> None:
    run = a_run()
    ports = ports_for(run, {SPEC_FILE: "spec", "elsewhere/file.md": "x"})

    tree = list_files_tree(ports, run.id)

    assert all(not entry.path.startswith("elsewhere") for entry in tree.entries)


def test_an_unknown_run_id_is_not_found() -> None:
    ports = RunFilesPorts(runs=FakeRunRepository(), workspace=FakeWorkspace)

    with pytest.raises(NotFound):
        list_files_tree(ports, new_id())


def test_a_run_with_no_worktree_yet_is_422_not_a_crash() -> None:
    run = a_run(worktree_path=None)
    ports = ports_for(run, {SPEC_FILE: "spec"})

    with pytest.raises(Invalid):
        list_files_tree(ports, run.id)


def test_the_initiative_folder_is_the_fallback_scope() -> None:
    run = a_run(inputs={"initiative_folder": SPEC_FOLDER})
    ports = ports_for(run, {SPEC_FILE: "spec"})

    tree = list_files_tree(ports, run.id)

    assert tree.root == SPEC_FOLDER
    assert any(entry.path == SPEC_FILE for entry in tree.entries)


def test_a_run_with_no_spec_folder_lists_nothing() -> None:
    """No `spec_folder`/`initiative_folder` (`repo-init@1`'s own shape): `_scope_folder`
    answers `""`, and this admits nothing — the same refusal `read_run_file`'s own
    `_within_spec_folder` draws for a read, not `workspace.tree("")`'s whole worktree,
    which would be the loophole that refusal exists to close (patch review, story 6-3)."""
    run = a_run(inputs={})
    ports = ports_for(run, {"README.md": "hello"})

    tree = list_files_tree(ports, run.id)

    assert tree.root == ""
    assert tree.entries == ()
