"""`write_run_file` (story 6-3, SPEC CAP-2, FR-19): the direct worktree write outside
`signal_run` — the five checks in their own order, the write itself (`Workspace.write` then
`Git.stage(worktree, pathspec=path)` + `Git.commit`), the one `spec_edit` gate record, and
the `uow.commit()` that lands them all together.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.run_files import (
    COMMIT_MESSAGE,
    PARKED_REQUIRED,
    PLANNED_AT,
    RunFilesWritePorts,
    write_run_file,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict, Forbidden, Invalid, NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.workspace import TreeEntry
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.runs import FakeGateRecordRepository, FakeRunRepository
from tests.unit.fakes.workspace import FakeWorkspace

SPEC_FOLDER = "specs/gates"
SPEC_FILE = f"{SPEC_FOLDER}/SPEC.md"
STORIES_FILE = f"{SPEC_FOLDER}/stories.yaml"
WORKTREE_PATH = "/work/acme/widgets/wt/gates"
NEW_CONTENT = "# SPEC\n\nedited by the operator\n"


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
        "worktree_path": WORKTREE_PATH,
        "park_path": "stories[0].build",
        "plan_refs": {},
        "terminal_session": False,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def ports_for(
    run: Run,
    files: dict[str, str] | None = None,
    *,
    git: FakeGit | None = None,
    clock: FakeClock | None = None,
    runs: FakeRunRepository | None = None,
) -> tuple[RunFilesWritePorts, FakeRunRepository, FakeGateRecordRepository, FakeUnitOfWork]:
    """One `FakeWorkspace` instance, returned by the factory every time it is asked — the
    use case calls `ports.workspace(...)` exactly once, but a test wants to inspect the same
    object afterward rather than a fresh copy of `files`."""
    run_repository = runs if runs is not None else FakeRunRepository([run])
    records = FakeGateRecordRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    workspace = FakeWorkspace(run.worktree_path, files=files or {})
    ports = RunFilesWritePorts(
        runs=run_repository,
        workspace=lambda root: workspace,
        git=git or FakeGit(),
        records=records,
        clock=clock or FakeClock(EPOCH),
        uow=uow,
    )
    return ports, run_repository, records, uow


def test_a_write_on_a_parked_run_writes_stages_commits_and_records() -> None:
    run = a_run()
    git = FakeGit()
    ports, runs, records, uow = ports_for(run, {SPEC_FILE: "old"}, git=git)

    result = write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)

    assert result == TreeEntry(path=SPEC_FILE, is_dir=False, size=len(NEW_CONTENT), mtime=0.0)
    assert git.called("stage") == [(Path(WORKTREE_PATH), SPEC_FILE)]
    assert git.called("commit") == [(Path(WORKTREE_PATH), COMMIT_MESSAGE)]
    assert len(records.records) == 1
    record = next(iter(records.records.values()))
    assert record.event == "spec_edit"
    assert record.actor == "operator"
    assert record.text == f"edited {SPEC_FILE}"
    assert record.path == run.park_path
    assert uow.committed is True
    assert ("get", run.id) in runs.calls


def test_the_written_content_is_readable_back() -> None:
    run = a_run()
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})

    write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)

    workspace = ports.workspace(run.worktree_path)
    assert workspace.read(SPEC_FILE) == NEW_CONTENT


def test_an_unknown_run_is_not_found() -> None:
    ports, *_ = ports_for(a_run(), runs=FakeRunRepository())

    with pytest.raises(NotFound):
        write_run_file(ports, new_id(), SPEC_FILE, NEW_CONTENT)


def test_a_path_that_escapes_the_workspace_is_422() -> None:
    run = a_run()
    ports, *_ = ports_for(run, {})

    with pytest.raises(Invalid):
        write_run_file(ports, run.id, "../x", NEW_CONTENT)


def test_a_well_formed_path_outside_the_spec_folder_is_403() -> None:
    run = a_run()
    ports, *_ = ports_for(run, {})

    with pytest.raises(Forbidden):
        write_run_file(ports, run.id, "elsewhere.md", NEW_CONTENT)


def test_a_list_file_the_plan_read_is_409_planned_at() -> None:
    run = a_run(plan_refs={STORIES_FILE: "abc1234"})
    ports, *_ = ports_for(run, {STORIES_FILE: "old"})

    with pytest.raises(Conflict, match=PLANNED_AT.format(sha="abc1234")):
        write_run_file(ports, run.id, STORIES_FILE, NEW_CONTENT)


def test_a_run_that_is_not_parked_is_409() -> None:
    run = a_run(status="running")
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})

    with pytest.raises(Conflict, match=PARKED_REQUIRED):
        write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)


def test_a_terminal_session_is_409_even_though_the_run_is_parked() -> None:
    run = a_run(terminal_session=True)
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})

    with pytest.raises(Conflict, match=PARKED_REQUIRED):
        write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)


def test_the_plan_anchor_refusal_is_checked_before_the_parked_refusal() -> None:
    """The code map's own order: 409 plan-anchor, then 409 parked — a list file on a Run
    that is *also* not parked still answers `PLANNED_AT`, never `PARKED_REQUIRED`."""
    run = a_run(status="running", plan_refs={STORIES_FILE: "deadbee"})
    ports, *_ = ports_for(run, {STORIES_FILE: "old"})

    with pytest.raises(Conflict, match=PLANNED_AT.format(sha="deadbee")):
        write_run_file(ports, run.id, STORIES_FILE, NEW_CONTENT)


def test_nothing_is_staged_or_committed_when_a_refusal_happens_first() -> None:
    run = a_run(status="running")
    git = FakeGit()
    ports, _, records, uow = ports_for(run, {SPEC_FILE: "old"}, git=git)

    with pytest.raises(Conflict):
        write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)

    assert git.called("stage") == []
    assert git.called("commit") == []
    assert records.records == {}
    assert uow.committed is False


def test_a_run_with_no_worktree_yet_is_422_not_a_crash() -> None:
    run = a_run(worktree_path=None)
    ports, *_ = ports_for(run, {})

    with pytest.raises(Invalid):
        write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)


def test_a_save_with_byte_identical_content_is_a_no_op() -> None:
    """`git commit` exits non-zero with nothing staged ("nothing to commit"), so a Save that
    changes nothing must never reach `stage`/`commit` at all — a 200 with the file's own
    current entry, no new commit, no new gate record (patch review, story 6-3)."""
    run = a_run()
    git = FakeGit()
    ports, _, records, uow = ports_for(run, {SPEC_FILE: NEW_CONTENT}, git=git)

    result = write_run_file(ports, run.id, SPEC_FILE, NEW_CONTENT)

    assert result == TreeEntry(path=SPEC_FILE, is_dir=False, size=len(NEW_CONTENT), mtime=0.0)
    assert git.called("stage") == []
    assert git.called("commit") == []
    assert records.records == {}
    assert uow.committed is False


def test_writing_to_a_path_that_is_a_directory_is_422() -> None:
    """`FakeWorkspace.write`'s own directory guard (mirroring `FsWorkspace`'s
    `IsADirectoryError`) is a `WorkspaceError`, caught the same way a rootless workspace is
    (patch review, story 6-3)."""
    run = a_run()
    ports, *_ = ports_for(run, {f"{SPEC_FOLDER}/stories/2-x.md": "story"})

    with pytest.raises(Invalid):
        write_run_file(ports, run.id, f"{SPEC_FOLDER}/stories", NEW_CONTENT)


def test_the_response_size_is_the_byte_length_not_the_character_count() -> None:
    """Multi-byte UTF-8 content: `RunFilesTree`'s own rows are `stat.st_size` (a byte
    count), and the write's own docstring says its result "is the same shape a tree row
    is" — a character count would silently disagree (patch review, story 6-3)."""
    run = a_run()
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})
    content = "café ☕\n"

    result = write_run_file(ports, run.id, SPEC_FILE, content)

    assert result.size == len(content.encode("utf-8"))
    assert result.size != len(content)


def test_the_response_size_matches_what_a_subsequent_tree_read_reports() -> None:
    run = a_run()
    ports, *_ = ports_for(run, {SPEC_FILE: "old"})
    content = "café ☕\n"

    result = write_run_file(ports, run.id, SPEC_FILE, content)

    workspace = ports.workspace(run.worktree_path)
    tree_row = next(entry for entry in workspace.tree(SPEC_FOLDER) if entry.path == SPEC_FILE)
    assert result.size == tree_row.size
