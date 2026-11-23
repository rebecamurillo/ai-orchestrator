"""`step_drawer` over the shared fakes (story 5, AC1-AC7)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.application.use_cases.run_step_drawer import (
    DrawerCommit,
    StepDrawerPorts,
    step_drawer,
)
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import NotFound
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import GitError
from orchestrator.domain.ports.git_history import FileStat
from tests.unit.fakes.git_history import FakeGitHistory
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.runs import FakeAttemptRepository, FakeRunRepository, FakeStepRunRepository

NOW = datetime(2026, 11, 23, tzinfo=UTC)
WORKTREE = "/work/run"
A = "a" * 40
B = "b" * 40
LATEST = 2
STAT = FileStat(path="src/x.py", added=3, removed=1)


def a_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "t",
        "template_version": 1,
        "status": "running",
        "budget_usd": Decimal("10"),
        "created_at": NOW,
        "worktree_path": WORKTREE,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def a_row(
    run: Run, *, seq: int = 1, path: str = "build", kind: str = "shell", **kw: object
) -> StepRun:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": run.id,
        "seq": seq,
        "path": path,
        "label": path,
        "kind": kind,
        "gate": "deterministic",
        "status": "done",
    }
    fields.update(kw)
    return StepRun(**fields)  # type: ignore[arg-type]


def an_attempt(row: StepRun, *, n: int = 1, **kw: object) -> Attempt:
    fields: dict[str, object] = {
        "id": new_id(),
        "run_id": row.run_id,
        "step_run_id": row.id,
        "n": n,
        "status": "done",
    }
    fields.update(kw)
    return Attempt(**fields)  # type: ignore[arg-type]


class Rig:
    def __init__(
        self,
        run: Run,
        rows: list[StepRun],
        attempts: list[Attempt],
        history: FakeGitHistory | None = None,
        logs: FakeLogReader | None = None,
    ) -> None:
        self.run = run
        self.history = history or FakeGitHistory()
        self.ports = StepDrawerPorts(
            runs=FakeRunRepository([run]),
            steps=FakeStepRunRepository(rows),
            attempts=FakeAttemptRepository(attempts),
            logs=logs or FakeLogReader(),
            history=self.history,
        )

    def drawer(self, seq: int = 1, n: int = 0):  # type: ignore[no-untyped-def]
        return step_drawer(self.ports, self.run.id, seq, n)


def test_agent_range_reads_files_with_counts() -> None:
    run = a_run()
    row = a_row(run, kind="agent")
    attempt = an_attempt(row, start_sha=A, end_sha=B)
    history = FakeGitHistory(stats={(WORKTREE, A, B): (STAT,)})

    written = Rig(run, [row], [attempt], history).drawer().files_written

    assert written.state == "files"
    assert written.files == (FileStat(path="src/x.py", added=3, removed=1),)


def test_a_workdir_roots_the_repo_and_prefixes_paths() -> None:
    run = a_run()
    row = a_row(run, kind="agent", with_resolved={"workdir": "repos/a"})
    attempt = an_attempt(row, start_sha=A, end_sha=B)
    history = FakeGitHistory(stats={(f"{WORKTREE}/repos/a", A, B): (STAT,)})

    written = Rig(run, [row], [attempt], history).drawer().files_written

    assert written.files[0].path == "repos/a/src/x.py"
    assert history.calls == [("diff_stat", str(Path(WORKTREE) / "repos/a"), A, B)]


def test_equal_shas_do_not_apply_rule_a() -> None:
    run = a_run()
    row = a_row(run, kind="agent")

    written = Rig(run, [row], [an_attempt(row, start_sha=A, end_sha=A)]).drawer().files_written

    assert written.state == "none"


def test_a_commit_row_reads_its_sha_and_subject() -> None:
    run = a_run()
    row = a_row(run, kind="git.commit", with_resolved={"workdir": "w"})
    attempt = an_attempt(row, output_ref="abc1234")
    repo = f"{WORKTREE}/w"
    history = FakeGitHistory(
        stats={(repo, "abc1234~1", "abc1234"): (STAT,)},
        subjects={(repo, "abc1234"): "story 1: x (orchestrator)"},
    )

    written = Rig(run, [row], [attempt], history).drawer().files_written

    assert written.state == "commit"
    assert written.commit == DrawerCommit("abc1234", "story 1: x (orchestrator)")
    assert written.files == (FileStat(path="w/src/x.py", added=3, removed=1),)


@pytest.mark.parametrize(("kind", "ref"), [("git.commit", "not a sha"), ("git.push", "abc1234")])
def test_rule_b_needs_a_commit_row_and_a_sha(kind: str, ref: str) -> None:
    run = a_run()
    row = a_row(run, kind=kind)

    written = Rig(run, [row], [an_attempt(row, output_ref=ref)]).drawer().files_written

    assert written.state == "none"


def test_a_sync_log_reads_its_refs() -> None:
    run = a_run()
    row = a_row(run, kind="git.sync")
    attempt = an_attempt(row, log_path="/logs/1")
    logs = FakeLogReader(lines_by_path={"/logs/1": ["x", "refs updated: feat/x aaaaaaa → bbbbbbb"]})

    written = Rig(run, [row], [attempt], logs=logs).drawer().files_written

    assert written.state == "refs"
    assert written.refs == ("feat/x aaaaaaa → bbbbbbb",)


def test_a_log_without_refs_lines_is_none() -> None:
    run = a_run()
    row = a_row(run, kind="git.push")
    attempt = an_attempt(row, log_path="/logs/1")
    logs = FakeLogReader(lines_by_path={"/logs/1": ["pushed"]})

    drawer = Rig(run, [row], [attempt], logs=logs).drawer()

    assert drawer.files_written.state == "none"
    assert drawer.files_read.state == "not_recorded"
    assert drawer.files_read.paths == ()


def test_a_push_with_no_log_path_is_none() -> None:
    run = a_run()
    row = a_row(run, kind="git.push")

    assert Rig(run, [row], [an_attempt(row)]).drawer().files_written.state == "none"


@pytest.mark.parametrize("which", ["error", "no_worktree"])
def test_git_error_and_missing_worktree_land_on_none(which: str) -> None:
    run = a_run(worktree_path=None) if which == "no_worktree" else a_run()
    row = a_row(run, kind="agent")
    attempt = an_attempt(row, start_sha=A, end_sha=B)
    history = FakeGitHistory(error=GitError(command="git", exit_code=1, output="bad"))

    assert Rig(run, [row], [attempt], history).drawer().files_written.state == "none"


def test_git_error_on_the_commit_rule_lands_on_none() -> None:
    run = a_run()
    row = a_row(run, kind="git.commit")
    history = FakeGitHistory(error=GitError(command="git", exit_code=1, output="bad"))

    rig = Rig(run, [row], [an_attempt(row, output_ref="abc1234")], history)

    assert rig.drawer().files_written.state == "none"


def test_a_skipped_row_with_no_attempt() -> None:
    run = a_run()
    row = a_row(run, status="skipped", reason="skipped · no command")

    drawer = Rig(run, [row], []).drawer()

    h = drawer.header
    assert (h.n, h.started_at, h.ended_at, h.exit_code, h.cost_usd) == (None,) * 5
    assert h.token == "SKP"
    assert drawer.attempts == ()
    assert drawer.log.attempt_id is None
    assert (drawer.log.state, drawer.log.removed_at) == ("not_run", None)
    assert drawer.log.reason == "skipped · no command"
    assert drawer.files_read.state == "none"
    assert drawer.files_written.state == "none"


def test_n_zero_is_the_latest_attempt_and_n_picks_one() -> None:
    run = a_run()
    row = a_row(run)
    first = an_attempt(row, n=1, status="error", log_path="/l/1", exit_code=1)
    second = an_attempt(
        row, n=2, started_at=NOW, ended_at=NOW, exit_code=0, cost_usd=Decimal("1.5")
    )
    logs = FakeLogReader(raw_by_path={"/l/1": b"one\n"})
    rig = Rig(run, [row], [second, first], logs=logs)

    latest = rig.drawer(n=0)
    one = rig.drawer(n=1)

    assert latest.header.n == LATEST
    assert latest.header.cost_usd == Decimal("1.5")
    assert [(a.n, a.status) for a in latest.attempts] == [(1, "error"), (2, "done")]
    assert latest.log.state == "no_output"
    assert one.header.n == 1
    assert one.header.exit_code == 1
    assert (one.log.attempt_id, one.log.state) == (first.id, "text")


def test_a_story_row_has_its_story_frame() -> None:
    run = a_run()
    rows = [
        a_row(run, seq=1, path="stories[0].prep"),
        a_row(run, seq=2, path="stories[0].dev", kind="agent"),
    ]

    drawer = Rig(run, rows, []).drawer(seq=1)

    assert drawer.run_order is not None
    assert drawer.run_order.frame == "stories[0]"


def test_a_row_in_no_frame_has_no_run_order() -> None:
    run = a_run()

    assert Rig(run, [a_row(run)], []).drawer().run_order is None


def test_unknown_run_seq_and_attempt_are_not_found() -> None:
    run = a_run()
    row = a_row(run)
    rig = Rig(run, [row], [an_attempt(row)])

    with pytest.raises(NotFound):
        step_drawer(rig.ports, new_id(), 1, 0)
    with pytest.raises(NotFound):
        rig.drawer(seq=9)
    with pytest.raises(NotFound):
        rig.drawer(n=3)
