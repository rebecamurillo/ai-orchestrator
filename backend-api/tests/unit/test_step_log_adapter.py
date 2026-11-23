"""`FsStepLog` writes a redacted, replaced, newline-terminated file at `log_path` (SPEC CAP-1)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from orchestrator.application.steps.context import log_path
from orchestrator.domain.ids import new_id
from orchestrator.infrastructure.process.step_log import FsStepLog
from tests.unit.step_fixtures import a_context, a_row

SECRET_A = "s3cr3t"
SECRET_B = "sk-test-b"


def test_a_secret_is_redacted_and_the_line_ends_with_a_newline(tmp_path: Path) -> None:
    run_id = new_id()

    path = FsStepLog(str(tmp_path), (SECRET_A,)).write(run_id, 7, 2, [f"token={SECRET_A}"])

    assert Path(path) == tmp_path / "logs" / str(run_id) / "007-2.log"
    assert Path(path).read_text() == "token=***\n"


def test_two_secrets_in_one_line_are_both_redacted(tmp_path: Path) -> None:
    path = FsStepLog(str(tmp_path), (SECRET_A, SECRET_B)).write(
        new_id(), 1, 1, [f"{SECRET_A} and {SECRET_B}"]
    )

    assert Path(path).read_text() == "*** and ***\n"


def test_no_lines_replace_existing_content_with_an_empty_file(tmp_path: Path) -> None:
    log = FsStepLog(str(tmp_path))
    run_id = new_id()
    first = log.write(run_id, 7, 2, ["old"])

    second = log.write(run_id, 7, 2, [])

    assert first == second
    assert Path(second).read_text() == ""


def test_the_return_value_is_the_path_the_executors_compute(tmp_path: Path) -> None:
    ctx = a_context(a_row(kind="git.checkout", with_resolved={}))
    ctx = replace(
        ctx,
        row=ctx.row.model_copy(update={"seq": 7}),
        attempt=ctx.attempt.model_copy(update={"n": 2}),
    )
    ctx = replace(ctx, ports=replace(ctx.ports, work_dir=str(tmp_path)))

    written = FsStepLog(str(tmp_path)).write(ctx.attempt.run_id, 7, 2, ["x"])

    assert written == str(log_path(ctx))
    assert written == f"{tmp_path}/logs/{ctx.attempt.run_id}/007-2.log"


def test_an_empty_secret_leaves_the_line_unchanged(tmp_path: Path) -> None:
    path = FsStepLog(str(tmp_path), ("", SECRET_A)).write(new_id(), 1, 1, ["abc"])

    assert Path(path).read_text() == "abc\n"
