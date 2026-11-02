"""A `verify_failed` consult inside the walker's own loop (story 1-6, spine AD-9/AD-10/AD-22,
2026-11-02).

`next_row → attempt_row → apply_result` over the real `agent` and `shell` executors: the gate
fails until the template's one redispatch is used up, the senior diagnoses the failure on the
build row, one further fresh redispatch carries the diagnosis beside the failure text, and the
next failure parks for a person without a second consult. The walker's sequence is the one it
always had, and no row ever resumes another row's session."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

# the real `agent` and `shell` executors register themselves on import (AD-9)
from orchestrator.application.steps import agent, shell
from orchestrator.application.steps.context import RunEnvironment, StepPorts
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.walk import WalkPorts, apply_result, attempt_row, next_row
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.ports.process import Outcome
from tests.unit.application.steps.agent_fixtures import RecordingEnv
from tests.unit.application.steps.agent_tail_fixtures import a_story, contracted
from tests.unit.application.verify_consult_fixtures import BLOCK
from tests.unit.application.writer_fixtures import World, a_world
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.logs import FakeLogReader
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.workspace import FakeWorkspace

BUILD = "stories[0].build"
VERIFY = "stories[0].verify"
PLAN: tuple[tuple[str, str], ...] = ((BUILD, agent.KIND), (VERIFY, shell.KIND))
WORKTREE = "/work/acme/widgets/wt/verify"
SPEC_FOLDER = "specs/verify"
MARKER = f"{SPEC_FOLDER}/stories/1-verify.md"
COMMAND = "make test"
HEAD = "7" * 40
LOG = Path("/work/logs/x.log")
AGENT_SESSION = "s-agent"
DIAGNOSIS = "The mock is stale; regenerate it."
CLAUSE = "BACK: {command} exited {code}: {tail}"
FAILING = Outcome(exit_code=2, timed_out=False, stalled=False)
PASSING = Outcome(exit_code=0, timed_out=False, stalled=False)
#: The agent starts, then is redispatched once; the third start is the senior's.
SENIOR_START = 3
#: The template's one redispatch and the senior's diagnosed one; the agent starts twice alone.
REDISPATCHES = 2
AGENT_STARTS = 2


class Loop:
    def __init__(self, *, consult: bool = True) -> None:
        build = contracted(
            expect=_expect(),
            spec_folder=SPEC_FOLDER,
            story_id="1",
            skill="staged-implement",
            harness="claude",
            prompts={
                "dispatch": "Run {skill} on {story_id}.",
                "answer": "Operator: {answer}",
                "redispatch": CLAUSE,
            },
        )
        route: dict[str, Any] = {"target_seq": 1, "max": 1}
        if consult:
            route["consult"] = BLOCK
        verify = {"command": COMMAND, "timeout_min": 30, "on_fail": route}
        self.world: World = a_world(
            "running",
            PLAN,
            None,
            {BUILD: build, VERIFY: verify},
            worktree_path=WORKTREE,
            budget_usd=Decimal("50.00"),
        )
        self.workspace = FakeWorkspace(files={MARKER: a_story("done")})
        self.harness = FakeHarness()
        self.process = FakeProcessRunner(outcomes={COMMAND: FAILING})
        self.git = FakeGit(status=[""], head_sha=[HEAD])
        self.world.ports = replace(self.world.ports, git=self.git)
        self.env = RecordingEnv()
        self.harness.results.extend(
            HarnessResult(session_id=f"s-{n}", exit_code=0, log_path=LOG) for n in range(8)
        )
        self.harness.on_wait = self._on_wait

    def _on_wait(self) -> None:
        """The third start is the senior writing its decision; any other is the agent."""
        if len(self.harness.called("start")) == SENIOR_START:
            decision = f"---\nstatus: answer\n---\n\n{DIAGNOSIS}\n"
            self.workspace.write(".orchestrator/consult/001-3.decision.md", decision)
        else:
            self.workspace.write(MARKER, a_story("done"))

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
                logs=FakeLogReader({}),
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

    def turn(self) -> str:
        """One pass of the walker's loop body over the row `next_row` answers."""
        seq = next_row(self.ports(), self.world.run.id)
        assert seq is not None
        result = attempt_row(self.ports(), self.world.run.id, seq, {"step": seq})
        return apply_result(self.ports(), self.world.run.id, seq, result)

    def turns(self, count: int) -> list[str]:
        return [self.turn() for _ in range(count)]


def _expect() -> dict[str, Any]:
    return {
        "files": [f"{SPEC_FOLDER}/stories/1-*.md"],
        "status_in": [],
        "success": ["done"],
        "blocked": ["blocked"],
        "checkpoint": ["ready-for-dev"],
        "misconfigured_when": [],
    }


#: build · verify fails · build (the template's redispatch) · verify fails and the bound is
#: used up · build (the senior's consult attempt) · build (the diagnosed redispatch)
TO_THE_DIAGNOSED_REDISPATCH = 6


def test_a_diagnosis_reaches_one_further_fresh_redispatch_and_a_pass_finishes_the_run() -> None:
    loop = Loop()
    loop.turns(TO_THE_DIAGNOSED_REDISPATCH)
    loop.process = FakeProcessRunner(outcomes={COMMAND: PASSING})

    statuses = loop.turns(1)

    assert statuses == ["done"]
    world = loop.world
    assert world.events() == ["redispatch", "consult", "senior_answer", "done"]
    assert world.stored_run().status == "done"


def test_the_diagnosis_is_told_in_a_new_session_beside_the_failure_text() -> None:
    loop = Loop()

    loop.turns(TO_THE_DIAGNOSED_REDISPATCH)

    assert loop.harness.called("resume") == []
    starts = loop.harness.called("start")
    assert len(starts) == SENIOR_START + 1
    assert starts[3]["prompt"].startswith(f"BACK: {COMMAND} exited ")
    assert DIAGNOSIS in starts[3]["prompt"]
    assert len({call["session_id"] for call in starts}) == len(starts)


def test_the_consult_attempt_belongs_to_the_build_row_and_the_senior_gets_the_facts() -> None:
    loop = Loop()

    loop.turns(TO_THE_DIAGNOSED_REDISPATCH)

    roles = [(a.n, a.role) for a in loop.world.attempts_of(BUILD)]
    assert roles == [(1, "agent"), (2, "agent"), (3, "consult"), (4, "agent")]
    senior = loop.harness.called("start")[2]
    assert COMMAND in senior["prompt"]
    assert senior["model"] == BLOCK["model"]
    build = loop.world.row(BUILD)
    assert build.redispatch_count == REDISPATCHES
    assert build.consults["verify_failed"]["state"] == "answer"


def test_the_next_failure_parks_for_a_person_and_never_consults_twice() -> None:
    loop = Loop()
    loop.turns(TO_THE_DIAGNOSED_REDISPATCH)

    status = loop.turn()

    assert status == "needs_you"
    world = loop.world
    run = world.stored_run()
    assert (run.park_kind, run.park_path) == ("verify_failed", VERIFY)
    assert run.park_reason == "verify failed 3/3"
    assert world.events().count("consult") == 1
    assert len(loop.harness.called("start")) == SENIOR_START + 1


def test_an_escalation_parks_the_verify_stop_once_with_the_seniors_reason() -> None:
    loop = Loop()
    loop.harness.on_wait = lambda: (
        loop.workspace.write(
            ".orchestrator/consult/001-3.decision.md",
            "---\nstatus: escalate\nreason: a product call\n---\n",
        )
        if len(loop.harness.called("start")) == SENIOR_START
        else loop.workspace.write(MARKER, a_story("done"))
    )

    statuses = loop.turns(5)

    assert statuses[-1] == "needs_you"
    world = loop.world
    run = world.stored_run()
    assert run.park_reason == "verify failed 2/2 · senior: a product call"
    assert (run.park_kind, run.park_path) == ("verify_failed", VERIFY)
    assert world.status_of(BUILD) == "done"
    assert world.events() == ["redispatch", "consult", "verify_failed"]


def test_a_gate_that_declares_no_consult_parks_as_it_always_did() -> None:
    loop = Loop(consult=False)

    statuses = loop.turns(4)

    assert statuses[-1] == "needs_you"
    assert loop.world.stored_run().park_reason == "verify failed 2/2"
    assert loop.world.events() == ["redispatch", "verify_failed"]
    assert len(loop.harness.called("start")) == AGENT_STARTS
