"""`GitRecorder` and its helpers (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from orchestrator.application.steps.context import log_path
from orchestrator.application.steps.step_log import (
    GitRecorder,
    head_or_none,
    logged,
    refs_line,
    write_step_log,
)
from orchestrator.domain.ports.git import NO_UPSTREAM, Git, GitError, RemoteRef
from orchestrator.domain.values import StepResult
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.step_log import FakeStepLog
from tests.unit.step_fixtures import a_context, a_row, without

W = Path("/w")


def recorder(**scripts: list[object]) -> GitRecorder:
    return GitRecorder(cast(Git, FakeGit(**scripts)))


def test_a_call_logs_its_operands_then_its_answer_lines_and_returns_the_answer() -> None:
    r = recorder(push=["pushed\nok"])

    answer = r.push(W, "feat", True, workdir="sub")

    assert answer == "pushed\nok"
    assert r.lines == ["> push /w feat True sub", "  pushed", "  ok"]


def test_none_adds_nothing_and_booleans_read_yes_or_no() -> None:
    r = recorder(stage=[None], base_exists=[True, False])

    r.stage(W)
    r.base_exists(W)
    r.base_exists(W)

    assert r.lines == ["> stage /w", "> base_exists /w", "  yes", "> base_exists /w", "  no"]


def test_a_tuple_logs_one_line_per_item_and_an_object_its_text() -> None:
    ref = RemoteRef(sha="a" * 40, ref="refs/heads/main")
    r = recorder(submodule_update=[("a", "b")], ls_remote=[ref])

    r.submodule_update(W)
    r.ls_remote("u")

    assert r.lines == ["> submodule_update /w", "  a", "  b", "> ls_remote u", f"  {ref}"]


def test_a_sentinel_answer_keeps_its_identity() -> None:
    r = recorder(merge=[NO_UPSTREAM])

    assert r.merge(W, "x") is NO_UPSTREAM


def test_read_file_logs_a_line_count_never_the_content() -> None:
    r = recorder(read_file=["a\nb\nc\n", None])

    r.read_file(W, "ref", "p")
    r.read_file(W, "ref", "p")

    assert r.lines == ["> read_file /w ref p", "  3 lines", "> read_file /w ref p", "  absent"]


def test_a_git_error_is_logged_and_re_raised_as_the_same_object() -> None:
    error = GitError(command="git fetch", exit_code=1, output="rejected")
    r = recorder(sync=[error])

    with pytest.raises(GitError) as raised:
        r.sync(W, "b")

    assert raised.value is error
    assert r.lines[-2:] == ["  error · exit 1", "  rejected"]


def test_a_non_callable_attribute_passes_through_unlogged() -> None:
    class Holder:
        value = "v"

    r = GitRecorder(cast(Git, Holder()))

    assert r.value == "v"  # type: ignore[attr-defined]
    assert r.lines == []


def test_write_step_log_answers_none_without_a_step_log_and_the_path_with_one() -> None:
    ctx = a_context(a_row(kind="git.sync", with_resolved={}))

    assert write_step_log(without(ctx, step_log=None), ["x"]) is None
    assert write_step_log(ctx, ["x"]) == str(log_path(ctx))
    fake = ctx.ports.step_log
    assert isinstance(fake, FakeStepLog)
    assert fake.writes == [(ctx.attempt.run_id, ctx.row.seq, ctx.attempt.n, ("x",))]


def test_logged_stores_the_lines_and_names_the_path_on_the_result() -> None:
    ctx = a_context(a_row(kind="git.sync", with_resolved={}))

    def body(inner: object, rec: GitRecorder) -> StepResult:
        rec.lines.append("> mark")
        return StepResult(status="done", gate="deterministic")

    result = logged(ctx, body)

    assert result.log_path == str(log_path(ctx))
    assert ctx.ports.step_log.writes[0][3] == ("> mark",)  # type: ignore[union-attr]


def test_logged_hands_the_body_a_context_whose_git_is_the_recorder() -> None:
    ctx = a_context(a_row(kind="git.sync", with_resolved={}))

    def body(inner: object, rec: GitRecorder) -> StepResult:
        inner.ports.git.head_sha(W)  # type: ignore[attr-defined]
        return StepResult(status="done", gate="deterministic")

    logged(ctx, body)

    assert ctx.ports.step_log.writes[0][3][0] == "> head_sha /w"  # type: ignore[union-attr]


def test_logged_writes_no_log_when_the_body_raises() -> None:
    ctx = a_context(a_row(kind="git.sync", with_resolved={}))

    def body(inner: object, rec: GitRecorder) -> StepResult:
        raise RuntimeError("wiring")

    with pytest.raises(RuntimeError):
        logged(ctx, body)
    assert ctx.ports.step_log.writes == []  # type: ignore[union-attr]


def test_refs_line_names_a_move_by_seven_characters_and_is_silent_otherwise() -> None:
    assert refs_line("a" * 40, "b" * 40, "feat") == "refs updated: feat aaaaaaa → bbbbbbb"
    assert refs_line("a" * 40, "a" * 40, "feat") is None
    assert refs_line(None, "b" * 40, "feat") is None
    assert refs_line("a" * 40, None, "feat") is None


def test_head_or_none_reads_a_failed_head_as_none() -> None:
    failed = GitError(command="git rev-parse", exit_code=124, output="timed out")
    assert head_or_none(cast(Git, FakeGit(head_sha=["a" * 40])), W) == "a" * 40
    assert head_or_none(cast(Git, FakeGit(head_sha=[failed])), W) is None
