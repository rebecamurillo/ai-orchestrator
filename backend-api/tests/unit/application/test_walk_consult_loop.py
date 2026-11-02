"""A consult inside the walker's own loop (story 1-4, spine AD-22, 2026-11-02).

`next_row → attempt_row → apply_result`, three times, through the real `agent` executor over
`FakeHarness`: the agent blocks, the senior answers, and the agent's own session resumes with
the senior's words. The Run never leaves `running`, no `blocked` record is written, and the
walker's sequence is the one it always had. A second stop then parks for a person, whose
`answer` resumes the same agent session."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

# the real `agent` executor registers itself on import (AD-9); the loop runs it, not a double
from orchestrator.application.steps.agent import KIND
from orchestrator.application.steps.context import RunEnvironment, StepPorts
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.walk import WalkPorts, apply_result, attempt_row, next_row
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.values import Signal
from tests.unit.application.consult_fixtures import planned
from tests.unit.application.steps.agent_fixtures import RecordingEnv
from tests.unit.application.steps.agent_tail_fixtures import a_section, a_story, contracted
from tests.unit.application.writer_fixtures import World, a_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace

BUILD = "stories[0].build"
PLAN: tuple[tuple[str, str], ...] = ((BUILD, KIND),)
WORKTREE = "/work/acme/widgets/wt/consult"
SPEC_FOLDER = "specs/consult"
STORY_ID = "1"
MARKER = f"{SPEC_FOLDER}/stories/{STORY_ID}-consult.md"
QUESTION = a_section("blocked", "which route?")
HEAD = "7" * 40
AGENT_SESSION = "s-agent"
SENIOR_ANSWER = "Use the v2 route."
LOG = Path("/work/logs/x.log")
#: The agent starts once; the second start is the senior's.
SENIOR_START = 2


class Loop:
    """The world, plus the doubles the executor reaches and what each recorded."""

    def __init__(self, consult: dict[str, Any] | None = None, **resolved: Any) -> None:
        extras = {"spec_folder": SPEC_FOLDER, "story_id": STORY_ID, **resolved}
        if consult is not None:
            extras["consult"] = consult
        self.world: World = a_world(
            "running",
            PLAN,
            None,
            {BUILD: contracted(expect=_expect(), **extras)},
            worktree_path=WORKTREE,
            budget_usd=Decimal("50.00"),
        )
        self.workspace = FakeWorkspace(files={MARKER: a_story("blocked", "which route?")})
        self.harness = FakeHarness()
        self.process = FakeProcessRunner()
        self.git = FakeGit(status=[""], head_sha=[HEAD])
        self.env = RecordingEnv()

    def ports(self) -> WalkPorts:
        world = self.world
        return WalkPorts(
            writers=world.ports,
            step=StepPorts(
                git=self.git,
                clock=world.clock,
                work_dir="/work",
                process=self.process,
                workspace=lambda _root: self.workspace,
                run_env=RunEnvironment(
                    run_id=world.run.id,
                    project_slug="acme",
                    repository_slug="widgets",
                    repository_url="https://github.com/acme/widgets.git",
                    default_branch="main",
                    bmad_version="6.11.0",
                    spec_folder=SPEC_FOLDER,
                    run=world.stored_run(),
                ),
                harnesses={"claude": self.harness},
                harness_env=self.env,
                attempt_writes=self._attempt_writes,
                spend_writes=self._spend_writes,
            ),
        )

    @contextmanager
    def _attempt_writes(self) -> Iterator[WriterPorts]:
        ports = self.world.ports
        yield WriterPorts(
            runs=ports.runs,
            steps=ports.steps,
            attempts=ports.attempts,
            records=ports.records,
            uow=FakeUnitOfWork(),
            clock=ports.clock,
        )

    @contextmanager
    def _spend_writes(self) -> Iterator[SpendPorts]:
        ports = self.world.ports
        yield SpendPorts(
            gateway=FakeGateway(),
            runs=ports.runs,
            steps=ports.steps,
            attempts=ports.attempts,
            uow=FakeUnitOfWork(),
        )

    def turn(self, resume: str | None = None) -> str:
        """One pass of the walker's loop body over the row `next_row` answers."""
        seq = next_row(self.ports(), self.world.run.id)
        assert seq is not None
        result = attempt_row(self.ports(), self.world.run.id, seq, {"step": seq}, resume)  # type: ignore[arg-type]
        return apply_result(self.ports(), self.world.run.id, seq, result)


def _expect() -> dict[str, Any]:
    return {
        "files": [f"{SPEC_FOLDER}/stories/{STORY_ID}-*.md"],
        "status_in": [],
        "success": ["done"],
        "blocked": ["blocked"],
        "checkpoint": ["ready-for-dev"],
        "misconfigured_when": [],
    }


def signal_ports(world: World) -> SignalPorts:
    return SignalPorts(
        writers=world.ports,
        engine=world.engine,
        harness_is_resumable=lambda name: True,
        latest_attempt_for_run=world.ports.attempts.latest_for_run,
    )


def the_senior_writes(loop: Loop, text: str) -> None:
    loop.workspace.write(".orchestrator/consult/001-2.decision.md", text)


def the_agent_finishes(loop: Loop, status: str = "done") -> None:
    loop.workspace.write(MARKER, a_story(status, "which route?" if status == "blocked" else None))


def script(loop: Loop) -> None:
    loop.harness.results.extend(
        [
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
            HarnessResult(session_id="s-senior", exit_code=0, log_path=LOG),
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
        ]
    )
    loop.harness.on_wait = lambda: (
        the_senior_writes(loop, f"---\nstatus: answer\n---\n\n{SENIOR_ANSWER}\n")
        if len(loop.harness.called("start")) == SENIOR_START
        else None
    )
    loop.harness.on_resume = lambda: the_agent_finishes(loop)


def test_the_senior_answers_and_the_agents_own_session_resumes() -> None:
    loop = Loop(consult=planned())
    script(loop)

    statuses = [loop.turn(), loop.turn(), loop.turn()]

    assert statuses == ["running", "running", "done"]
    world = loop.world
    assert "blocked" not in world.events()
    assert world.events() == ["consult", "senior_answer", "done"]
    [resumed] = loop.harness.called("resume")
    assert resumed["session_id"] == AGENT_SESSION
    assert resumed["message"] == (
        f'Answer from the senior reviewer to the blocking condition "{QUESTION}": {SENIOR_ANSWER}'
    )
    roles = [(a.n, a.role) for a in world.attempts_of(BUILD)]
    assert roles == [(1, "agent"), (2, "consult"), (3, "agent")]
    assert world.row(BUILD).retry_count == 0


def test_on_fail_fail_does_not_end_an_offered_run() -> None:
    loop = Loop(consult=planned(), on_fail="fail")
    script(loop)

    assert loop.turn() == "running"

    assert loop.world.stored_run().status == "running"
    assert loop.world.attempts_of(BUILD)[-1].role == "agent"
    seq = next_row(loop.ports(), loop.world.run.id)
    attempt_row(loop.ports(), loop.world.run.id, seq or 0, {})
    assert loop.world.attempts_of(BUILD)[-1].role == "consult"


def test_a_second_stop_parks_and_the_operators_answer_resumes_the_agents_session() -> None:
    loop = Loop(consult=planned())
    script(loop)
    loop.harness.on_resume = lambda: the_agent_finishes(loop, "blocked")
    loop.turn()
    loop.turn()

    assert loop.turn() == "needs_you"

    world = loop.world
    assert world.events()[-1] == "blocked"
    signal_run(
        signal_ports(world),
        world.run.id,
        Signal(kind="answer", payload={"text": "Ship it.", "mode": "session"}),
    )
    loop.harness.results.append(HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG))
    loop.harness.on_resume = lambda: the_agent_finishes(loop)
    assert loop.turn("answer") == "done"
    assert [call["session_id"] for call in loop.harness.called("resume")] == [AGENT_SESSION] * 2
    assert len(loop.harness.called("start")) == SENIOR_START


def test_an_escalation_parks_once_and_the_operator_resumes_attempt_ones_session() -> None:
    loop = Loop(consult=planned())
    loop.harness.results.extend(
        [
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
            HarnessResult(session_id="s-senior", exit_code=0, log_path=LOG),
            HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG),
        ]
    )
    loop.harness.on_wait = lambda: the_senior_writes(
        loop, "---\nstatus: escalate\nreason: a product decision\n---\n"
    )
    loop.turn()

    assert loop.turn() == "needs_you"

    world = loop.world
    assert world.events() == ["consult", "blocked"]
    assert world.stored_run().park_reason == f"{QUESTION} · senior: a product decision"
    signal_run(
        signal_ports(world),
        world.run.id,
        Signal(kind="answer", payload={"text": "Ship it."}),
    )
    loop.harness.on_resume = lambda: the_agent_finishes(loop)
    assert loop.turn("answer") == "done"
    [resumed] = loop.harness.called("resume")
    assert resumed["session_id"] == AGENT_SESSION


def test_a_row_without_a_consult_parks_as_today() -> None:
    loop = Loop()
    loop.harness.results.append(HarnessResult(session_id=AGENT_SESSION, exit_code=0, log_path=LOG))

    assert loop.turn() == "needs_you"

    assert loop.world.events() == ["blocked"]
