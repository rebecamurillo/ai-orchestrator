"""The walker resolving why a `verify` row sent a Story back (FR-10, AD-8, AD-9).

`walk._context` is the only place holding both the row about to run and the repositories, so
it is where the three facts a redispatched `agent` row needs are read: the failed `verify`
row's own command, the exit code its latest attempt recorded, and the last 200 lines of that
attempt's log. They travel on `RunEnvironment` as one frozen `VerifyFailure`, which is the
move `_frame_start_sha` already makes — the executor reads a value and never a repository.

Nothing here is about what the executor then writes; that is
`tests/unit/application/steps/test_agent_retry_dispatch.py`. What is asserted here is that
the walker looks the facts up, that it looks them up only for a row that was actually sent
back, and that a Run whose ports carry no `LogReader` degrades rather than raising.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.context import RunEnvironment, VerifyFailure
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.use_cases.walk import VERIFY_LOG_LINES, WalkPorts, run_row
from orchestrator.domain.values import StepResult
from tests.unit.application.writer_fixtures import EPIC_PLAN, World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.logs import FakeLogReader

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
BUILD_SEQ = 5
COMMAND = "make test"
LOG = "/work/logs/run/006-1.log"
LINES = ["FAILED tests/a.py::test_x", "1 failed, 12 passed"]
#: FR-10's own bound, restated here so the constant cannot be lowered unnoticed.
TAIL_LINES = 200
WORK_DIR = "/work"


class Recording:
    """An executor that answers `done` and keeps the context it was handed."""

    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    """`agent` bound to a recording executor for the length of one test."""
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("agent", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def a_redispatched_run(
    *, redispatch_count: int = 1, on_fail: dict[str, Any] | None = None, attempts: bool = True
) -> World:
    """A Run whose `build` row was sent back by the `verify` row that failed on it."""
    resolved = {
        VERIFY: {
            "command": COMMAND,
            "on_fail": on_fail if on_fail is not None else {"target_seq": BUILD_SEQ, "max": 1},
        }
    }
    world = a_world("running", EPIC_PLAN, {BUILD: "running", VERIFY: "done"}, resolved)
    world.ports.steps.update(
        world.row(BUILD).model_copy(update={"redispatch_count": redispatch_count})
    )
    an_attempt(world, BUILD, n=2)
    if attempts:
        an_attempt(world, VERIFY, n=1, status="error", exit_code=1, log_path=LOG)
    return world


def ports_of(world: World, logs: FakeLogReader | None = None) -> WalkPorts:
    return WalkPorts(
        writers=world.ports,
        step=StepPorts(
            git=FakeGit(),
            clock=FakeClock(EPOCH),
            work_dir=WORK_DIR,
            run_env=RunEnvironment(
                run_id=world.run.id,
                project_slug="acme",
                repository_slug="widgets",
                repository_url="https://github.com/acme/widgets.git",
                default_branch="main",
                bmad_version="6.11.0",
                spec_folder="specs/notifications",
            ),
            logs=logs if logs is not None else FakeLogReader({LOG: LINES}),
        ),
    )


def resolved_failure(world: World, logs: FakeLogReader | None = None) -> VerifyFailure | None:
    ports = ports_of(world, logs)
    run_row(ports, world.run.id, BUILD_SEQ)
    seen = EXECUTORS["agent"]
    assert isinstance(seen, Recording)
    environment = seen.seen[-1].ports.run_env
    assert environment is not None
    return environment.verify_failure


@pytest.mark.usefixtures("executor")
def test_the_command_the_code_and_the_log_tail_reach_the_row_that_was_sent_back() -> None:
    failure = resolved_failure(a_redispatched_run())

    assert failure == VerifyFailure(command=COMMAND, exit_code=1, log_tail=tuple(LINES))


@pytest.mark.usefixtures("executor")
def test_the_tail_is_the_last_two_hundred_lines_and_says_so() -> None:
    logs = FakeLogReader({LOG: LINES})

    resolved_failure(a_redispatched_run(), logs)

    assert logs.calls == [(LOG, VERIFY_LOG_LINES)]
    assert VERIFY_LOG_LINES == TAIL_LINES


@pytest.mark.usefixtures("executor")
def test_a_row_that_was_never_sent_back_resolves_nothing() -> None:
    """The lookup is not free, and a row on its first attempt has no failure to describe."""
    assert resolved_failure(a_redispatched_run(redispatch_count=0)) is None


@pytest.mark.usefixtures("executor")
def test_a_row_no_other_row_redispatches_to_resolves_nothing() -> None:
    world = a_redispatched_run(on_fail={"target_seq": 99, "max": 1})

    assert resolved_failure(world) is None


@pytest.mark.usefixtures("executor")
def test_a_plain_word_on_fail_is_not_a_route_back_to_anything() -> None:
    """`fail`, `continue` and the absent `escalate` name no target (AD-9)."""
    world = a_redispatched_run(on_fail={})

    assert resolved_failure(world) is None


@pytest.mark.usefixtures("executor")
def test_a_verify_row_that_never_ran_an_attempt_still_names_its_command() -> None:
    """The Operator gets the command even when there is no code and no log to show."""
    failure = resolved_failure(a_redispatched_run(attempts=False))

    assert failure == VerifyFailure(command=COMMAND, exit_code=None, log_tail=())


@pytest.mark.usefixtures("executor")
def test_a_walker_with_no_log_reader_wired_reports_the_facts_it_has() -> None:
    """`StepPorts.logs` is `None` in every construction predating this story: the command
    and the code still reach the row, and the tail is simply empty."""
    world = a_redispatched_run()
    wired = ports_of(world)
    ports = WalkPorts(writers=wired.writers, step=replace(wired.step, logs=None))

    run_row(ports, world.run.id, BUILD_SEQ)

    seen = EXECUTORS["agent"]
    assert isinstance(seen, Recording)
    environment = seen.seen[-1].ports.run_env
    assert environment is not None
    assert environment.verify_failure == VerifyFailure(command=COMMAND, exit_code=1, log_tail=())


@pytest.mark.usefixtures("executor")
def test_a_walker_that_resolved_no_environment_at_all_hands_the_ports_over_unchanged() -> None:
    world = a_redispatched_run()
    ports = WalkPorts(
        writers=world.ports,
        step=StepPorts(git=FakeGit(), clock=FakeClock(EPOCH), work_dir=WORK_DIR),
    )

    run_row(ports, world.run.id, BUILD_SEQ)

    seen = EXECUTORS["agent"]
    assert isinstance(seen, Recording)
    assert seen.seen[-1].ports is ports.step
