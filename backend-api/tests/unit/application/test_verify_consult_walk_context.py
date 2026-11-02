"""`walk_context.context` and a `verify_failed` diagnosis (story 1-6, spine AD-9/AD-10/AD-22,
2026-11-02).

The diagnosis rides on `VerifyFailure`, beside the command and the log tail the failed gate
left, so it reaches a fresh redispatch through the existing redispatch clause. It is never the
row's `resume_signal`: that would resume the old session, which AD-10 forbids for this stop."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.steps.registry import EXECUTORS, register
from orchestrator.application.steps.verify_failure import VerifyFailure
from orchestrator.application.use_cases.walk import WalkPorts, run_row
from orchestrator.application.use_cases.writers import Entry, record
from orchestrator.domain.values import StepResult
from tests.unit.application.verify_consult_fixtures import BUILD, VERIFY, a_verify_world
from tests.unit.application.writer_fixtures import World, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.logs import FakeLogReader

LOG = "/work/logs/run/006-1.log"
ANSWERED = {"verify_failed": {"state": "answer", "answered_by": 4}}
DIAGNOSIS = 'Diagnosis of "verify failed 3/3": the mock is stale.'


class Recording:
    def __init__(self) -> None:
        self.seen: list[StepContext] = []

    def execute(self, ctx: StepContext) -> StepResult:
        self.seen.append(ctx)
        return StepResult(status="done", gate=ctx.row.gate)


@pytest.fixture
def executor() -> Iterator[Recording]:
    kept = dict(EXECUTORS)
    EXECUTORS.clear()
    recording = Recording()
    register("agent", recording)
    yield recording
    EXECUTORS.clear()
    EXECUTORS.update(kept)


def a_diagnosed_world(consults: dict[str, object] | None = ANSWERED) -> World:
    """Agent attempts 1-3, the consult 4, and the redispatch attempt 5 about to run."""
    world = a_verify_world(build="running", consults=consults)  # type: ignore[arg-type]
    an_attempt(world, VERIFY, n=1, status="error", exit_code=2, log_path=LOG)
    an_attempt(world, BUILD, n=3, status="done", end_sha="e" * 40)
    an_attempt(world, BUILD, n=4, role="consult", status="error", session_id="s-senior")
    an_attempt(world, BUILD, n=5)
    return world


def senior_answer(world: World, kind: str = "verify_failed") -> None:
    record(
        world.ports,
        world.run,
        Entry(
            event="senior_answer",
            actor="senior",
            path=BUILD,
            attempt_n=4,
            payload={"text": DIAGNOSIS, "kind": kind},
        ),
    )


def resolved(world: World) -> StepContext:
    ports = WalkPorts(
        writers=world.ports,
        step=StepPorts(
            git=FakeGit(),
            clock=FakeClock(EPOCH),
            work_dir="/work",
            run_env=RunEnvironment(
                run_id=world.run.id,
                project_slug="acme",
                repository_slug="widgets",
                repository_url="https://github.com/acme/widgets.git",
                default_branch="main",
                bmad_version="6.11.0",
                spec_folder="specs",
            ),
            logs=FakeLogReader({LOG: ["1 failed"]}),
        ),
    )
    run_row(ports, world.run.id, world.row(BUILD).seq)
    seen = EXECUTORS["agent"]
    assert isinstance(seen, Recording)
    return seen.seen[-1]


@pytest.mark.usefixtures("executor")
def test_the_owed_diagnosis_rides_on_the_verify_failure() -> None:
    world = a_diagnosed_world()
    senior_answer(world)

    ctx = resolved(world)

    failure = ctx.ports.run_env.verify_failure  # type: ignore[union-attr]
    assert failure == VerifyFailure(
        command="make test", exit_code=2, log_tail=("1 failed",), diagnosis=DIAGNOSIS
    )


@pytest.mark.usefixtures("executor")
def test_the_diagnosis_is_not_the_resume_signal() -> None:
    world = a_diagnosed_world()
    senior_answer(world)

    ctx = resolved(world)

    assert ctx.resume_signal is None
    assert ctx.previous_attempt is not None
    assert (ctx.previous_attempt.n, ctx.attempt.role) == (3, "agent")


@pytest.mark.usefixtures("executor")
def test_a_diagnosis_already_delivered_is_not_owed_again() -> None:
    world = a_diagnosed_world()
    senior_answer(world)
    an_attempt(world, BUILD, n=6, status="done", end_sha="f" * 40)

    ctx = resolved(world)

    assert ctx.ports.run_env.verify_failure.diagnosis == ""  # type: ignore[union-attr]


@pytest.mark.usefixtures("executor")
def test_a_failure_nobody_diagnosed_carries_none() -> None:
    world = a_diagnosed_world(consults={})
    senior_answer(world)

    ctx = resolved(world)

    assert ctx.ports.run_env.verify_failure.diagnosis == ""  # type: ignore[union-attr]


@pytest.mark.usefixtures("executor")
def test_a_blocked_answer_is_not_a_diagnosis() -> None:
    world = a_diagnosed_world(consults={"blocked": {"state": "answer", "answered_by": 4}})
    senior_answer(world, kind="blocked")

    ctx = resolved(world)

    assert ctx.ports.run_env.verify_failure.diagnosis == ""  # type: ignore[union-attr]
    assert ctx.resume_signal is not None
