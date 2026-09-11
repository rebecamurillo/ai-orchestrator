"""`apply_step_result`'s log half: the file the row's process wrote, recorded on the Attempt.

AD-8 closes the attempt here — `ended_at`, the status the row reached, `output_ref` — and the
spine's field list puts `log_path` on `attempt` for any row, not only an `agent` one. This is
the seam that puts it there for the rest: a deterministic kind cannot reach an
`AttemptRepository` (its `StepPorts` holds no repository at all), so it returns the name and
the writer records it, inside the unit of work the row's own transitions are already in.

One rule is worth its own test. The `agent` kind writes `log_path` itself, through
`AttemptRepository.mark_finished`, the moment the harness exits and *before* this runs
(`steps/agent_tail.py`). Its result carries no name, so a writer that wrote the field
unconditionally would blank what the harness recorded. A result names a log or says nothing
about one; it never un-names it.
"""

from __future__ import annotations

from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.domain.values import Park, StepResult
from tests.unit.application.writer_fixtures import PAIR_PLAN, World, a_world, an_attempt

#: What `steps/context.py::log_path` computes for the first attempt of the second row.
LOG = "/work/logs/01a08f32-48e3-7689-b3f2-5942b6164707/002-1.log"
#: A second file, so "the attempt kept its own" cannot pass by coincidence.
HARNESS_LOG = "/work/logs/01a08f32-48e3-7689-b3f2-5942b6164707/003-1.log"

FAILED = "install failed: exit 127"


def a_world_on_its_second_row() -> World:
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    an_attempt(world, "checkout")
    return world


def the_attempt(world: World, path: str) -> object:
    row = world.row(path)
    return world.ports.attempts.get_latest(row.id)


def test_a_result_that_names_a_log_records_it_on_the_attempt() -> None:
    world = a_world_on_its_second_row()

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(status="done", gate="deterministic", output_ref=LOG, log_path=LOG),
    )

    attempt = the_attempt(world, "checkout")
    assert attempt is not None
    assert attempt.log_path == LOG


def test_a_parked_failure_records_its_log_too() -> None:
    """The whole point: a `misconfigured` stop is the row an Operator opens, and the tail
    is the only thing on it that says what the command printed."""
    world = a_world_on_its_second_row()

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(
            status="error",
            gate="deterministic",
            output_ref=LOG,
            log_path=LOG,
            reason=FAILED,
            park=Park(kind="misconfigured", reason=FAILED, path="checkout"),
        ),
    )

    run = world.ports.runs.get(world.run.id)
    assert run is not None
    assert run.status == "needs_you"
    attempt = the_attempt(world, "checkout")
    assert attempt is not None
    assert attempt.log_path == LOG


def test_a_result_that_names_no_log_leaves_the_attempt_s_own_alone() -> None:
    """What the `agent` kind already recorded through `mark_finished` survives this."""
    world = a_world("running", PAIR_PLAN, {"plan": "done", "checkout": "running"})
    an_attempt(world, "checkout", log_path=HARNESS_LOG)

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(status="done", gate="liveness", output_ref=HARNESS_LOG),
    )

    attempt = the_attempt(world, "checkout")
    assert attempt is not None
    assert attempt.log_path == HARNESS_LOG


def test_a_row_that_started_no_process_leaves_the_column_unset() -> None:
    """`checkpoint`, `git.commit`, `pr.link` — nothing appended a file for these."""
    world = a_world_on_its_second_row()

    apply_step_result(
        world.ports,
        world.run.id,
        2,
        StepResult(status="done", gate="deterministic", output_ref="9e1d2c3"),
    )

    attempt = the_attempt(world, "checkout")
    assert attempt is not None
    assert attempt.log_path is None
