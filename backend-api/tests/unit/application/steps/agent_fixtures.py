"""One wired world for the `agent` kind's three test modules (AD-18: fakes are shared).

`tests/unit/step_fixtures.py` is frozen and knows none of the ports this kind needs — the
harness registry, the environment builder, the attempt writes — so the context is built
here instead. Nothing new is faked: every double below is the one shared fake for its port,
and the two small recorders are not ports at all.

`attempt_writes` opens a **fresh** `FakeUnitOfWork` per call over one shared
`FakeAttemptRepository`, because that is what the production wiring does
(`open_writer_ports` opens a session per scope) and because `FakeUnitOfWork` refuses a
second entry. `World.uows` is therefore one entry per write, which is how "three writes,
three transactions" (AD-8) is asserted, and `World.attempts.calls` is the ordered method
log the pgid-before-await proof reads.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from uuid import UUID

from orchestrator.application.steps.context import (
    ProjectContext,
    RunEnvironment,
    StepContext,
    StepPorts,
)
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from orchestrator.domain.statuses import GateEvent
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.process import FakeProcessRunner
from tests.unit.fakes.runs import FakeAttemptRepository
from tests.unit.fakes.tracer import FakeTracer
from tests.unit.fakes.workspace import FakeWorkspace

WORK_DIR = "/work"
PROJECT_SLUG = "acme"
WORKTREE = "/work/acme/widgets/wt/feat-x"
#: The row path the shipped `epic@1` plan gives a Story's `build` step — the one the
#: timeout sentence in this story's acceptance criteria is written with.
ROW_PATH = "epics[0].stories[3].build"
STORY_ID = "4-1"
SPEC_FOLDER = "specs/notifications"
SKILL = "bmad-build-auto"
PROMPT_EXTRA = "Read X."
HARNESS_NAME = "claude"
MODEL = "claude-opus-5"
BUDGET = Decimal("10.00")
SPEND = Decimal("2.50")
HEAD_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"


class RecordingEnv:
    """Stands in for `HarnessEnv`: records every fact it was given, answers a dict.

    Not a port double in the `tests/unit/fakes/` sense — `HarnessEnv` is a callable, and
    what a test needs of it is that the executor passed the attempt, the Run's slug, the
    Project's variables and the span's `traceparent`, and handed the answer on unchanged.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(  # noqa: PLR0913 — the port's own signature
        self,
        attempt: Attempt,
        *,
        run: Run,
        project_slug: str,
        project_env: Any,
        log_content: bool,
        story_id: str | None,
        traceparent: str,
    ) -> dict[str, str]:
        self.calls.append(
            {
                "attempt": attempt,
                "run": run,
                "project_slug": project_slug,
                "project_env": dict(project_env),
                "log_content": log_content,
                "story_id": story_id,
                "traceparent": traceparent,
            }
        )
        return {
            "ORCH_PROJECT": project_slug,
            "ORCH_STORY_ID": story_id or "",
            "TRACEPARENT": traceparent,
            **dict(project_env),
        }


@dataclass
class World:
    """One wired context, plus every double a test reads its assertions back out of."""

    ctx: StepContext
    run: Run
    row: StepRun
    attempt: Attempt
    git: FakeGit
    clock: FakeClock
    process: FakeProcessRunner
    workspace: FakeWorkspace
    harness: FakeHarness
    tracer: FakeTracer | None
    harness_env: RecordingEnv
    attempts: FakeAttemptRepository
    uows: list[FakeUnitOfWork] = field(default_factory=list)


def a_run(**over: Any) -> Run:
    fields: dict[str, Any] = {
        "id": new_id(),
        "project_id": new_id(),
        "repository_id": new_id(),
        "template_name": "story",
        "template_version": 1,
        "status": "running",
        "budget_usd": BUDGET,
        "spend_usd": SPEND,
        "created_at": EPOCH,
        "worktree_path": WORKTREE,
    }
    fields.update(over)
    return Run(**fields)


def resolved(**over: Any) -> dict[str, Any]:
    """The `with_resolved` an `agent` row carries, as the planner leaves it (AD-7).

    Operator revision 2026-09-15: `timeout_min` is no longer present by default (agent steps
    carry no wall-clock deadline unless the template sets one explicitly); `stall_min` is
    present with the kind's own default of 30.
    """
    row: dict[str, Any] = {
        "harness": HARNESS_NAME,
        "model": MODEL,
        "skill": SKILL,
        "args": {"spec_folder": SPEC_FOLDER, "story_id": STORY_ID},
        "prompt_extra": PROMPT_EXTRA,
        "story_id": STORY_ID,
        "spec_folder": SPEC_FOLDER,
        "spec_checkpoint": False,
        "stall_min": 30,
    }
    row.update(over)
    return row


def an_agent_row(
    with_resolved: dict[str, Any] | None = None, *, seq: int = 3, run_id: UUID | None = None
) -> StepRun:
    return StepRun(
        id=new_id(),
        run_id=run_id if run_id is not None else new_id(),
        seq=seq,
        path=ROW_PATH,
        label="build",
        kind="agent",
        gate="liveness",
        status="running",
        story_id=STORY_ID,
        with_resolved=with_resolved if with_resolved is not None else resolved(),
    )


def a_gate_record(
    row: StepRun, event: GateEvent, payload: dict[str, Any] | None = None
) -> GateRecord:
    return GateRecord(
        id=new_id(),
        run_id=row.run_id,
        at=EPOCH,
        event=event,
        actor="operator",
        path=row.path,
        text="",
        payload=payload or {},
    )


def an_attempt(row: StepRun, n: int, **over: Any) -> Attempt:
    fields: dict[str, Any] = {
        "id": new_id(),
        "run_id": row.run_id,
        "step_run_id": row.id,
        "n": n,
        "status": "running",
        "started_at": EPOCH,
    }
    fields.update(over)
    return Attempt(**fields)


def a_world(  # noqa: PLR0913 — one keyword per double or context field, each optional
    *,
    with_resolved: dict[str, Any] | None = None,
    files: dict[str, str] | None = None,
    git: FakeGit | None = None,
    harness: FakeHarness | None = None,
    harnesses: dict[str, Any] | None = None,
    tracer: FakeTracer | None = None,
    previous: Attempt | None = None,
    resume: GateRecord | None = None,
    project: ProjectContext | None = None,
    test_globs: tuple[str, ...] = (),
    run: Run | None = None,
    cwd: str | None = WORKTREE,
    clock: FakeClock | None = None,
    writes_failing_on: int | None = None,
    process: FakeProcessRunner | None = None,
    skill_catalog: Any = None,
) -> World:
    """One `agent` row, wired to the shared fakes, ready to `AgentExecutor().execute(...)`."""
    the_run = run if run is not None else a_run()
    row = an_agent_row(with_resolved, run_id=the_run.id)
    attempt = an_attempt(row, 2 if previous is not None else 1)
    repository = FakeAttemptRepository([*([previous] if previous is not None else []), attempt])
    uows: list[FakeUnitOfWork] = []
    the_harness = harness if harness is not None else FakeHarness()
    the_clock = clock if clock is not None else FakeClock()
    the_git = git if git is not None else FakeGit(head_sha=[HEAD_SHA])
    workspace = FakeWorkspace(files=files or {})
    harness_env = RecordingEnv()
    context = StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=cwd,
        frame_start_sha=None,
        previous_attempt=previous,
        attempt=attempt,
        resume_signal=resume,
        ports=StepPorts(
            git=the_git,
            clock=the_clock,
            work_dir=WORK_DIR,
            process=process if process is not None else FakeProcessRunner(),
            workspace=lambda _root: workspace,
            run_env=RunEnvironment(
                run_id=the_run.id,
                project_slug=PROJECT_SLUG,
                repository_slug="widgets",
                repository_url="https://github.com/acme/widgets.git",
                default_branch="main",
                install_command="",
                bmad_version="6.11.0",
                spec_folder=SPEC_FOLDER,
                run=the_run,
                project=project if project is not None else ProjectContext(),
                test_globs=test_globs,
            ),
            tracer=tracer,
            harnesses=harnesses if harnesses is not None else {HARNESS_NAME: the_harness},
            harness_env=harness_env,
            attempt_writes=_writes(repository, uows, the_clock, writes_failing_on),
            # `None` by default, which is how every world built before the hub-Run
            # operations skills install fix (2026-09-24) keeps dispatching unchanged:
            # `steps/agent_skill.py` refuses nothing without a catalog to refuse it by.
            skill_catalog=skill_catalog,
        ),
    )
    ports = context.ports
    assert ports.process is not None
    assert ports.workspace is not None
    return World(
        ctx=context,
        run=the_run,
        row=row,
        attempt=attempt,
        git=the_git,
        clock=the_clock,
        process=ports.process,
        workspace=workspace,
        harness=the_harness,
        tracer=tracer,
        harness_env=harness_env,
        attempts=repository,
        uows=uows,
    )


def _writes(
    attempts: FakeAttemptRepository,
    uows: list[FakeUnitOfWork],
    clock: FakeClock,
    failing_on: int | None = None,
) -> Any:
    """`StepPorts.attempt_writes`: a fresh scope, and a fresh transaction, per write.

    `failing_on` is a 1-based call number that raises instead of yielding — how a test
    reaches "the database went away between `Harness.start` and `Harness.wait`", which is
    the one moment a lost write can orphan a running harness (AD-14).
    """

    @contextmanager
    def open_scope() -> Iterator[WriterPorts]:
        uow = FakeUnitOfWork()
        uows.append(uow)
        if failing_on is not None and len(uows) == failing_on:
            raise WriteFailed(failing_on)
        yield WriterPorts(
            runs=_refused("runs"),
            steps=_refused("steps"),
            attempts=attempts,
            records=_refused("records"),
            uow=uow,
            clock=clock,
        )

    return open_scope


class WriteFailed(RuntimeError):
    """What a scripted attempt-write failure raises — a database that went away mid-row."""

    def __init__(self, call: int) -> None:
        super().__init__(f"attempt write {call} failed")


class _Refusing:
    """A repository the `agent` executor must never reach (AD-8): any call is the failure."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __getattr__(self, item: str) -> Any:
        raise AssertionError(f"the agent executor touched WriterPorts.{self.name}.{item}")


def _refused(name: str) -> Any:
    return _Refusing(name)
