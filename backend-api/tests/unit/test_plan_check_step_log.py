"""`plan.check` writes its log (story 2 of epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.steps.context import StepContext, log_path
from orchestrator.application.steps.plan_check import KIND, PlanCheckExecutor
from tests.unit.fakes.git import FakeGit
from tests.unit.step_fixtures import a_context, a_row, without

SHA = "c" * 40


def a_check_context(git: FakeGit, *, resume: str | None = None, stale: bool = False) -> StepContext:
    row = a_row(
        kind=KIND,
        path="plan",
        with_resolved={
            "timeout_min": 5,
            "base_dir": "/work/p/r/base",
            "url": "https://example.test/o/r.git",
            "base_branch": "main",
            "plan_refs": {"stories.yaml": SHA},
            "list_branches": {},
        },
    )
    return a_context(row, git=git, resume=resume)  # type: ignore[arg-type]


def test_the_list_file_is_logged_as_a_line_count_never_its_content() -> None:
    git = FakeGit(read_file=["- id: 1\n- id: 2\n"], refs={"main": SHA})
    ctx = a_check_context(git)

    result = PlanCheckExecutor().execute(ctx)

    assert result.log_path == str(log_path(ctx))
    lines = ctx.ports.step_log.writes[0][3]  # type: ignore[union-attr]
    assert any(line.startswith("> read_file ") for line in lines)
    assert "  2 lines" in lines
    assert not [line for line in lines if "id:" in line]
    assert not [line for line in lines if line.startswith("refs updated:")]


def test_a_continue_and_a_stale_plan_both_carry_the_log_and_keep_their_fields() -> None:
    cases = [("continue", FakeGit()), (None, FakeGit(read_file=["changed\n"]))]
    for resume, git in cases:
        ctx = a_check_context(git, resume=resume)
        bare = without(a_check_context(git, resume=resume), step_log=None)

        result = PlanCheckExecutor().execute(ctx)
        plain = PlanCheckExecutor().execute(bare)

        assert result.log_path == str(log_path(ctx))
        assert plain.log_path is None
        assert plain.model_dump(exclude={"log_path"}) == result.model_dump(exclude={"log_path"})
