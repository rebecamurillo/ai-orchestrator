"""`apply_step_result` stores the `log_path` a `git.commit` result names (story 2 of
epic-1-step-logs, AD-40)."""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import StepResult
from tests.unit.application.test_attempt_log_path import a_world_on_its_second_row, the_attempt

LOG = "/work/logs/01a08f32-48e3-7689-b3f2-5942b6164707/002-1.log"


def test_a_commit_result_that_names_its_step_log_is_recorded_on_the_attempt() -> None:
    world = a_world_on_its_second_row()

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(status="done", gate="deterministic", output_ref="9e1d2c3", log_path=LOG),
    )

    attempt = the_attempt(world, "checkout")
    assert attempt is not None
    assert attempt.log_path == LOG
