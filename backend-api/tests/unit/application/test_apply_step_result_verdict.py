"""`apply_step_result` stores a gate verdict on the closing attempt (epic 8 story 2, AC1-AC5)."""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import GateVerdict, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt


def a_running() -> World:
    return a_world("running", PAIR_PLAN, {"plan": "running"})


def test_a_done_result_stores_the_verdict_on_the_latest_attempt() -> None:
    world = a_running()
    an_attempt(world, "plan", 1)
    verdict = GateVerdict(word="fail", fields={"owners": ["ux", "tech"]}, text="- a\n- b")

    apply_step_result(
        world.ports, world.run.id, 1, StepResult(status="done", gate="liveness", verdict=verdict)
    )

    [attempt] = world.attempts_of("plan")
    assert world.status_of("plan") == "done"
    assert attempt.verdict_word == "fail"
    assert attempt.verdict_fields == {"owners": ["ux", "tech"]}
    assert attempt.verdict_text == "- a\n- b"


def test_a_result_without_a_verdict_leaves_the_columns_null() -> None:
    world = a_running()
    an_attempt(world, "plan", 1)

    apply_step_result(world.ports, world.run.id, 1, StepResult(status="done", gate="liveness"))

    [attempt] = world.attempts_of("plan")
    assert (attempt.verdict_word, attempt.verdict_fields, attempt.verdict_text) == (None,) * 3


def test_a_verdict_never_blanks_the_log_path() -> None:
    world = a_running()
    an_attempt(world, "plan", 1, log_path="/work/logs/1.log")

    apply_step_result(
        world.ports,
        world.run.id,
        1,
        StepResult(status="done", gate="liveness", verdict=GateVerdict(word="pass")),
    )

    [attempt] = world.attempts_of("plan")
    assert attempt.log_path == "/work/logs/1.log"
    assert attempt.verdict_word == "pass"
