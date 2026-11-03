"""An open senior session wired for its turns (story 2-5, AD-21, AD-23).

`session_fixtures.SessionWorld` plus what a turn reaches beyond the signals: the step ports
`walk_context.context` hands the turn, with attempt and spend writes opening a fresh
`FakeUnitOfWork` per scope over the world's own repositories, as `open_writer_ports` opens a
session per scope. Every double is a shared fake (AD-18).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from orchestrator.application.steps.context import RunEnvironment, StepPorts
from orchestrator.application.use_cases.session_turn import (
    MessagePorts,
    TurnPorts,
    commit_turn,
    post_message,
    run_turn,
)
from orchestrator.application.use_cases.session_view import SessionTurn
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.ports.harness import HarnessResult
from orchestrator.domain.ports.workspace import Workspace
from tests.unit.application.session_fixtures import (
    BUILD,
    SPEC_FOLDER,
    WORKTREE,
    SessionWorld,
    a_session_world,
    probing,
)
from tests.unit.application.steps.agent_fixtures import RecordingEnv
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.gateway import FakeGateway
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.skill_catalog import FakeSkillCatalog
from tests.unit.fakes.tracer import FakeTracer
from tests.unit.fakes.workspace import FakeWorkspace

STORY_ID = "1"
ROW: dict[str, Any] = {
    "harness": "claude",
    "model": "claude-sonnet",
    "spec_folder": SPEC_FOLDER,
    "story_id": STORY_ID,
    "stall_min": 30,
}
LOG = "/work/logs/{run_id}/005-{n}.log"


@dataclass
class TurnWorld:
    """The session, the turn's doubles, and every recorder a test reads back."""

    session: SessionWorld
    harness: FakeHarness
    process: FakeProcessRunner = field(default_factory=FakeProcessRunner)
    gateway: FakeGateway = field(default_factory=FakeGateway)
    tracer: FakeTracer = field(default_factory=FakeTracer)
    harness_env: RecordingEnv = field(default_factory=RecordingEnv)
    workspaces: dict[str | None, FakeWorkspace] = field(default_factory=dict)
    spend_uows: list[FakeUnitOfWork] = field(default_factory=list)
    #: The 1-based attempt write that raises instead of opening: a database gone mid-turn.
    failing_write: int | None = None
    writes: int = 0
    traced: bool = True
    #: A `Workspace` factory of a test's own, such as `FsWorkspace` over a real tree.
    workspace_factory: Callable[[str | None], Workspace] | None = None

    @property
    def git(self) -> FakeGit:
        return self.session.git

    @property
    def writers(self) -> WriterPorts:
        return self.session.world.ports

    def workspace(self, root: str | None = WORKTREE) -> FakeWorkspace:
        return self.workspaces.setdefault(root, FakeWorkspace(root=root))

    @property
    def step(self) -> StepPorts:
        return StepPorts(
            git=self.git,
            clock=self.session.world.clock,
            work_dir="/work",
            process=self.process,
            workspace=self.workspace_factory or self.workspace,
            tracer=self.tracer if self.traced else None,
            harnesses={"claude": self.harness},
            harness_env=self.harness_env,
            attempt_writes=self._attempt_writes,
            spend_writes=self._spend_writes,
        )

    @property
    def ports(self) -> TurnPorts:
        return TurnPorts(writers=self.writers, step=self.step, read_environment=self._environment)

    @property
    def messages(self) -> MessagePorts:
        return MessagePorts(writers=self.writers, engine=self.session.world.engine)

    def post(self, text: str = "Why is the route missing?") -> SessionTurn:
        return post_message(self.messages, self.session.world.run.id, text)

    def run(self, attempt_id: UUID) -> None:
        run_turn(self.ports, attempt_id)

    def commit(self, attempt_id: UUID) -> None:
        commit_turn(self.ports, attempt_id)

    def turn(self, text: str = "Why is the route missing?") -> Attempt:
        """One message, run and committed, as the workflow runs it."""
        posted = self.post(text)
        self.run(posted.attempt_id)
        self.commit(posted.attempt_id)
        return self.attempt(posted.attempt_id)

    def attempt(self, attempt_id: UUID) -> Attempt:
        stored = self.writers.attempts.get(attempt_id)
        assert stored is not None
        return stored

    def _environment(self, run_id: UUID) -> RunEnvironment:
        return RunEnvironment(
            run_id=run_id,
            project_slug="demo",
            repository_slug="app",
            repository_url="https://github.com/acme/app.git",
            default_branch="main",
            bmad_version="6.0.0",
            spec_folder=SPEC_FOLDER,
            run=self.session.world.stored_run(),
        )

    @contextmanager
    def _attempt_writes(self) -> Iterator[WriterPorts]:
        self.writes += 1
        if self.writes == self.failing_write:
            raise RuntimeError(f"attempt write {self.writes} failed")
        world = self.session.world
        yield WriterPorts(
            runs=world.ports.runs,
            steps=world.ports.steps,
            attempts=world.ports.attempts,
            records=world.ports.records,
            uow=FakeUnitOfWork(),
            clock=world.clock,
        )

    @contextmanager
    def _spend_writes(self) -> Iterator[SpendPorts]:
        uow = FakeUnitOfWork()
        self.spend_uows.append(uow)
        world = self.session.world
        yield SpendPorts(
            gateway=self.gateway,
            runs=world.ports.runs,
            steps=world.ports.steps,
            attempts=world.ports.attempts,
            uow=uow,
        )


def a_result(**over: Any) -> HarnessResult:
    fields: dict[str, Any] = {"session_id": "s-1", "exit_code": 0, "log_path": Path("/work/x.log")}
    fields.update(over)
    return HarnessResult(**fields)


def a_turn_world(
    *,
    git: FakeGit | None = None,
    results: list[HarnessResult] | None = None,
    with_resolved: dict[str, Any] | None = None,
    start: bool = True,
    **over: Any,
) -> TurnWorld:
    """A `blocked` stop on `BUILD` with a story-scoped session opened on `claude`."""
    harness = probing()
    harness.results = list(results or [])
    session = a_session_world(
        git=git or FakeGit(),
        harnesses={"claude": harness},
        with_resolved={BUILD: with_resolved if with_resolved is not None else dict(ROW)},
        **over,
    )
    world = TurnWorld(session=session, harness=harness)
    if start:
        session.start()
    return world


def skilled() -> FakeSkillCatalog:
    return FakeSkillCatalog(frozenset({"senior-session"}))
