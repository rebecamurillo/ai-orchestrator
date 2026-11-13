"""Analysis inputs: scratch clone, base rule, declaration, commits not made by the Run
(story 5.1, AC1-AC7, AC14)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.analysis.declaration import DECLARATION_FILE
from orchestrator.application.analysis.inputs import (
    AttemptRange,
    attempt_ranges,
    prepare_analysis,
    slug,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run_records import RunCommit, RunRepositoryRecord
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ports.git import GitError
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_analysis import AnalysisScript
from tests.unit.fakes.workspace import FakeWorkspace

RUN = UUID(int=1)
CALCULATION = UUID(int=2)
WORK = Path("/work")
NOW = datetime(2026, 11, 13, tzinfo=UTC)


def record(path: str = ".", head: str | None = "h1", n: int = 10) -> RunRepositoryRecord:
    return RunRepositoryRecord(
        id=UUID(int=n),
        run_id=RUN,
        path=path,
        remote_url=f"https://example.invalid/{n}.git",
        base_branch="main",
        head_pushed=head,
    )


def commit(path: str, sha: str, n: int) -> RunCommit:
    return RunCommit(id=UUID(int=n), run_id=RUN, path=path, sha=sha, made_by="wip", at=NOW)


class Ids:
    def __init__(self) -> None:
        self.issued: list[UUID] = []

    def __call__(self) -> UUID:
        made = UUID(int=100 + len(self.issued))
        self.issued.append(made)
        return made


def prepare(  # noqa: PLR0913 — one keyword per fixture a case varies
    git: FakeGit,
    records: list[RunRepositoryRecord],
    *,
    commits: list[RunCommit] | None = None,
    ranges: list[AttemptRange] | None = None,
    scratch: FakeWorkspace | None = None,
    ids: Ids | None = None,
):  # type: ignore[no-untyped-def]
    return prepare_analysis(
        run_id=RUN,
        calculation_id=CALCULATION,
        records=records,
        commits=commits or [],
        ranges=ranges or [],
        git=git,
        scratch_root=scratch or FakeWorkspace(),
        work_dir=WORK,
        new_id=ids or Ids(),
        clock=FakeClock(NOW),
    )


def diverged() -> FakeGit:
    return FakeGit(analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}))


def test_base_is_the_merge_base_and_head_is_the_pushed_commit() -> None:  # AC1
    git = diverged()
    with prepare(git, [record()]) as (inputs,):
        assert (inputs.analysis.base, inputs.analysis.head) == ("m0", "h1")
        assert inputs.analysis.status == "ok"
        assert inputs.scratch == WORK / "analysis" / str(UUID(int=100)) / "root"
        assert inputs.analysis.repository_path == "."
    fetches = [args for name, args in git.calls if name == "fetch"]
    assert [refs for _, refs, _ in fetches] == [
        ("+refs/heads/main:refs/remotes/origin/main",),
        ("h1",),
    ]
    assert ("merge_base", (inputs.scratch, "h1", "origin/main")) in git.calls


def test_no_pushed_head_fails_that_repository_only() -> None:  # AC2
    git = FakeGit(analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}))
    member = record("repos/x", head=None, n=11)
    with prepare(git, [member, record()]) as (first, second):
        assert first.analysis.status == "failed"
        assert first.analysis.output == "commit missing: no pushed head"
        assert first.scratch is None
        assert second.analysis.status == "ok"
    urls = [args[0] for name, args in git.calls if name == "fetch"]
    assert member.remote_url not in urls


def test_a_head_the_remote_does_not_hold_fails_without_another_commit() -> None:  # AC3
    error = GitError(command="git fetch", exit_code=128, output="not our ref h9")
    git = FakeGit(analysis=AnalysisScript(fetch={"h9": error}))
    with prepare(git, [record(head="h9")]) as (inputs,):
        assert inputs.analysis.status == "failed"
        assert inputs.analysis.output.splitlines()[0] == "commit missing: h9"
        assert "not our ref h9" in inputs.analysis.output
        assert inputs.analysis.head is None
    assert not [name for name, _ in git.calls if name == "merge_base"]


def test_a_base_branch_fetch_failure_is_the_git_output() -> None:
    error = GitError(command="git fetch", exit_code=128, output="no such branch")
    git = FakeGit(
        analysis=AnalysisScript(fetch={"+refs/heads/main:refs/remotes/origin/main": error})
    )
    with prepare(git, [record()]) as (inputs,):
        assert (inputs.analysis.status, inputs.analysis.output) == ("failed", "no such branch")


def test_no_merge_base_fails() -> None:
    with prepare(FakeGit(), [record()]) as (inputs,):
        assert inputs.analysis.status == "failed"
        assert inputs.analysis.output == "no merge base: h1 and origin/main"


@pytest.mark.parametrize("method", ["merge_base", "read_file", "commits_between"])
def test_a_git_timeout_after_the_fetch_fails_that_repository_only(
    method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = FakeGit(analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}), files={})

    def times_out(*_: object) -> None:
        raise GitError(command=f"git {method}", exit_code=124, output="timeout after 60 s")

    monkeypatch.setattr(git, method, times_out)
    member = record("repos/x", n=11)
    with prepare(git, [member, record()]) as (first, second):
        assert (first.analysis.status, first.analysis.output) == ("failed", "timeout after 60 s")
        assert (first.analysis.base, first.analysis.head) == (None, None)
        assert second.analysis.status == "failed"
    fetched = [args[0] for name, args in git.calls if name == "fetch"]
    assert record().remote_url in fetched


def test_commits_not_made_by_the_run_are_the_rest_of_the_range() -> None:  # AC4
    git = FakeGit(
        analysis=AnalysisScript(
            merge_bases={("h1", "origin/main"): "m0"},
            commits={
                ("m0", "h1"): ("c3", "c2", "c1"),
                ("s", "e"): ("c2",),
                ("s2", "e2"): ("c3",),
            },
        )
    )
    with prepare(
        git,
        [record()],
        commits=[commit(".", "c1", 1), commit("repos/other", "c3", 2)],
        ranges=[AttemptRange(".", "s", "e"), AttemptRange("repos/other", "s2", "e2")],
    ) as (inputs,):
        assert inputs.commits_not_made_by_run == ("c3",)


def test_the_declaration_is_read_at_the_base_only() -> None:  # AC5
    text = "tier2: true\ntests:\n  unit: ['a/**']\n"
    git = FakeGit(
        analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}),
        files={("m0", DECLARATION_FILE): text, ("h1", DECLARATION_FILE): "tier2: false\n"},
    )
    with prepare(git, [record()]) as (inputs,):
        assert inputs.declaration.tier2 is True
        assert inputs.declaration.tests_unit == ("a/**",)
        assert inputs.analysis.declaration_hash == hashlib.sha256(text.encode()).hexdigest()
    reads = [args[1] for name, args in git.calls if name == "read_file"]
    assert reads == ["m0"]


def test_no_declaration_is_the_defaults() -> None:  # AC6
    with prepare(diverged(), [record()]) as (inputs,):
        assert inputs.analysis.declaration_hash is None
        assert inputs.analysis.status == "ok"
        assert inputs.declaration.tier2 is False


@pytest.mark.parametrize(
    ("text", "named"), [("foo: 1\ntier2: true\n", "foo"), ("commands:\n  foo: x\n", "commands.foo")]
)
def test_an_unknown_key_makes_it_partial(text: str, named: str) -> None:  # AC7
    git = FakeGit(
        analysis=AnalysisScript(merge_bases={("h1", "origin/main"): "m0"}),
        files={("m0", DECLARATION_FILE): text},
    )
    with prepare(git, [record()]) as (inputs,):
        assert inputs.analysis.status == "partial"
        assert named in inputs.analysis.output


def test_the_hub_is_the_root_with_members() -> None:
    git = diverged()
    with prepare(git, [record(), record("repos/x", n=11)]) as (root, member):
        assert root.hub is True and member.hub is False
    with prepare(diverged(), [record()]) as (alone,):
        assert alone.hub is False


def test_slugs() -> None:
    assert slug(".") == "root"
    assert slug("repos/x") == "repos-x"


def test_the_scratch_folder_of_every_analysis_is_removed_after_a_normal_end() -> None:  # AC14
    scratch = FakeWorkspace(files={})
    ids = Ids()
    removed: list[str] = []
    scratch.remove = removed.append  # type: ignore[method-assign]
    with prepare(diverged(), [record(), record("repos/x", None, 11)], scratch=scratch, ids=ids):
        assert removed == []
    assert removed == [str(i) for i in ids.issued]
    assert len(removed) == 2  # noqa: PLR2004


def test_the_scratch_folder_is_removed_when_the_calculation_raises() -> None:  # AC14
    scratch = FakeWorkspace()
    removed: list[str] = []
    scratch.remove = removed.append  # type: ignore[method-assign]
    ids = Ids()
    with pytest.raises(RuntimeError), prepare(diverged(), [record()], scratch=scratch, ids=ids):
        raise RuntimeError("boom")
    assert removed == [str(ids.issued[0])]


def test_a_failure_while_preparing_still_removes_what_was_allocated() -> None:
    scratch = FakeWorkspace()
    removed: list[str] = []
    scratch.remove = removed.append  # type: ignore[method-assign]

    class Exploding(FakeGit):
        def merge_base(self, dest: Path, a: str, b: str) -> str | None:
            raise OSError("disk")

    ids = Ids()
    with pytest.raises(OSError), prepare(Exploding(), [record()], scratch=scratch, ids=ids):
        pass
    assert removed == [str(ids.issued[0])]


def attempt(**over: object) -> Attempt:
    return Attempt.model_construct(**over)


def row(workdir: str | None) -> StepRun:
    return StepRun.model_construct(with_resolved={"workdir": workdir} if workdir else {})


def test_attempt_ranges_for_a_root_row_a_workdir_row_and_an_open_attempt() -> None:
    pairs = [
        (attempt(start_sha="a", end_sha="b", root_start_sha=None, root_end_sha=None), row(None)),
        (
            attempt(start_sha="s", end_sha="e", root_start_sha="rs", root_end_sha="re"),
            row("repos/x"),
        ),
        (attempt(start_sha="o", end_sha=None, root_start_sha=None, root_end_sha=None), row(None)),
        (attempt(start_sha=None, end_sha="z", root_start_sha=None, root_end_sha=None), row(None)),
        (
            attempt(start_sha="s", end_sha="e", root_start_sha=None, root_end_sha=None),
            row("repos/x"),
        ),
        (
            attempt(start_sha="a", end_sha="b", root_start_sha=None, root_end_sha=None),
            row("unknown"),
        ),
    ]
    assert attempt_ranges(pairs, ["repos/x"]) == (
        AttemptRange(".", "a", "b"),
        AttemptRange("repos/x", "s", "e"),
        AttemptRange(".", "rs", "re"),
        AttemptRange("repos/x", "s", "e"),
        AttemptRange(".", "a", "b"),
    )
