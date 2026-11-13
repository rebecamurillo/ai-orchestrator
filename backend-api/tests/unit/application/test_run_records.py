"""`submodule_url`, `heads_at_end` and `ended`, and `set_run`'s terminal write (story 2, AC5)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.application.use_cases.run_records import ended, heads_at_end, submodule_url
from orchestrator.application.use_cases.writers import set_run
from orchestrator.domain.entities.run_records import RunRepositoryRecord
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from tests.unit.application.writer_fixtures import a_world
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.run_records import FakeRunRepositoryRecords

HUB = "https://h/o/hub.git"
MODULES = """[submodule "a"]
\tpath = repos/a
\turl = ../a.git
[submodule "b"]
\tpath = repos/b
\turl = https://elsewhere/b.git
[submodule "c"]
\tpath = repos/c
\turl = ./x
[submodule "d"]
\tpath = repos/d
"""


def test_a_relative_url_resolves_against_the_superproject() -> None:
    assert submodule_url(MODULES, "repos/a", HUB) == "https://h/o/a.git"
    assert submodule_url(MODULES, "repos/a", "git@h:o/hub.git") == "git@h:o/a.git"
    assert submodule_url(MODULES, "repos/a", "git@h:hub.git") == "git@h:a.git"
    assert submodule_url(MODULES, "repos/c", HUB) == "https://h/o/hub.git/x"


def test_an_absolute_url_is_kept_and_the_path_is_normalised() -> None:
    assert submodule_url(MODULES, "./repos/b/", HUB) == "https://elsewhere/b.git"


def test_no_match_or_no_text_is_empty() -> None:
    assert submodule_url(MODULES, "repos/z", HUB) == ""
    assert submodule_url(MODULES, "repos/d", HUB) == ""
    assert submodule_url(None, "repos/a", HUB) == ""
    assert submodule_url("path = repos/a\nurl = x", "repos/a", HUB) == ""


def a_record(run_id: object, path: str) -> RunRepositoryRecord:
    return RunRepositoryRecord(
        id=new_id(),
        run_id=run_id,  # type: ignore[arg-type]
        path=path,
        remote_url="u",
        base_branch="main",
        branch="b",
        base_tip="t",
    )


def a_run_with_rows(**over: object):  # type: ignore[no-untyped-def]
    world = a_world("running", worktree_path="/wt", **over)
    records = FakeRunRepositoryRecords()
    for path in (".", "repos/a"):
        records.add(a_record(world.run.id, path))
    return world, records


def test_heads_at_end_reads_each_tree_and_skips_the_unanswerable() -> None:
    world, records = a_run_with_rows()
    git = FakeGit(heads={"/wt": ["h0"], str(Path("/wt/repos/a")): [None]})
    heads_at_end(git, records, world.run)
    assert {r.path: r.head_local_at_end for r in records.rows} == {".": "h0", "repos/a": None}


def test_a_git_error_leaves_that_row_null() -> None:
    world, records = a_run_with_rows()
    git = FakeGit(head_sha=[GitError(command="x", exit_code=1, output=""), "h1"])
    heads_at_end(git, records, world.run)
    assert {r.path: r.head_local_at_end for r in records.rows} == {".": None, "repos/a": "h1"}


def test_no_worktree_writes_nothing() -> None:
    world, records = a_run_with_rows()
    run = world.run.model_copy(update={"worktree_path": None})
    git = FakeGit()
    heads_at_end(git, records, run)
    assert git.calls == []
    assert all(r.head_local_at_end is None for r in records.rows)


@pytest.mark.parametrize("terminal", ["done", "failed", "cancelled"])
def test_set_run_to_terminal_writes_the_heads(terminal: str) -> None:
    world, records = a_run_with_rows()
    ports = replace(
        world.ports,
        git=FakeGit(heads={"/wt": ["h0"], "/wt/repos/a": ["h1"]}),
        run_repositories=records,
    )
    set_run(ports, world.run, status=terminal)
    assert {r.path: r.head_local_at_end for r in records.rows} == {".": "h0", "repos/a": "h1"}


def test_other_writes_call_no_head_sha() -> None:
    world, records = a_run_with_rows()
    git = FakeGit()
    ports = replace(world.ports, git=git, run_repositories=records)
    set_run(ports, world.run, status="needs_you")
    done = world.run.model_copy(update={"status": "done"})
    set_run(ports, done, status="failed")
    assert git.called("head_sha") == []


def test_unset_ports_do_nothing() -> None:
    world, records = a_run_with_rows()
    after = world.run.model_copy(update={"status": "done"})
    ended(None, records, world.run, after)
    ended(FakeGit(), None, world.run, after)
    assert all(r.head_local_at_end is None for r in records.rows)


def test_a_failing_head_read_is_logged_and_the_terminal_write_still_lands() -> None:
    world, records = a_run_with_rows()
    ports = replace(
        world.ports, git=FakeGit(head_sha=[OSError("no git")]), run_repositories=records
    )
    updated = set_run(ports, world.run, status="done")
    assert updated.status == "done"
    assert all(r.head_local_at_end is None for r in records.rows)
