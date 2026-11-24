"""The conversation close check: `step_close` and the `continue` after its own park run the
session's anchor diff first (epic 5 story 2, 2026-11-23; AD-17 amended, R1).

Imports `orchestrator.application.use_cases.conversation_close` by path.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Any

from orchestrator.application.steps import StepContext, StepPorts
from orchestrator.application.steps.context import RunEnvironment
from orchestrator.application.steps.conversation import ConversationExecutor
from orchestrator.application.use_cases import conversation_close
from orchestrator.application.use_cases.apply_step_result import apply_step_result
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.run import Run
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.git import Change
from tests.unit.application.writer_fixtures import World, a_world, an_attempt
from tests.unit.fakes.clock import EPOCH, FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit

TREE = "/work/wt"
WRITES = ["epics.yaml", "*/SPEC.md", "*/stories.yaml"]
INPUTS = {"initiative_folder": "initiatives", "slug": "demo"}
PLAN = (("tech", "conversation"), ("after", "conversation"))
EDITS = (
    Change(path="initiatives/demo/epics.yaml", kind="modified"),
    Change(path="backend-api/AGENTS.md", kind="modified"),
)


def a_closing_world(
    *, accepted: tuple[str, ...] = (), start_sha: str | None = "s0", **row: Any
) -> World:
    world = a_world(
        "running",
        PLAN,
        {"tech": "running", "after": "planned"},
        {"tech": {"step": "tech", "writes": WRITES, **row}, "after": {"step": "after"}},
        inputs=INPUTS,
        worktree_path=TREE,
        accepted_paths=accepted,
        lane="interactive",
    )
    world.ports.records.add(
        GateRecord(
            id=new_id(), run_id=world.run.id, at=EPOCH, event="session_start", actor="machine"
        )
    )
    an_attempt(world, "tech")
    an_attempt(
        world,
        "tech",
        n=2,
        role="session",
        started_at=EPOCH + timedelta(seconds=1),
        start_sha=start_sha,
    )
    stored = world.stored_run()
    return World(run=stored, ports=world.ports, engine=world.engine, clock=world.clock)


def context_of(world: World, event: str, git: FakeGit) -> StepContext:
    row = world.row("tech")
    environment = RunEnvironment(
        run_id=world.run.id,
        project_slug="acme",
        repository_slug="widgets",
        repository_url="u",
        default_branch="main",
        bmad_version="6.11.0",
        spec_folder=None,
        run=world.run,
        plan_rows=tuple(world.ports.steps.list_for_run(world.run.id)),
    )

    @contextmanager
    def writes() -> Iterator[WriterPorts]:
        yield WriterPorts(
            runs=world.ports.runs,
            steps=world.ports.steps,
            attempts=world.ports.attempts,
            records=world.ports.records,
            uow=FakeUnitOfWork(),
            clock=world.clock,
        )

    record = GateRecord(id=new_id(), run_id=world.run.id, event=event, actor="operator", at=EPOCH)  # type: ignore[arg-type]
    return StepContext(
        row=row,
        with_resolved=row.with_resolved,
        cwd=TREE,
        frame_start_sha=None,
        previous_attempt=None,
        attempt=world.attempts_of("tech")[0],
        resume_signal=record,
        ports=StepPorts(
            git=git,
            clock=FakeClock(EPOCH),
            work_dir="/work",
            run_env=environment,
            attempt_writes=writes,
        ),
    )


def a_git() -> FakeGit:
    return FakeGit(heads={TREE: ["h1"]}, changes={TREE: EDITS}, statuses={TREE: ""})


def test_ac5_a_step_close_with_an_out_of_writes_anchor_parks_protected_path() -> None:
    world = a_closing_world()

    result = ConversationExecutor().execute(context_of(world, "step_close", a_git()))

    assert result.status == "error"
    assert result.park is not None
    assert (result.park.kind, result.park.path) == ("protected_path", "tech")
    assert result.park.reason == "protected paths: backend-api/AGENTS.md"
    assert result.payload["hits"] == [{"path": "backend-api/AGENTS.md"}]
    apply_step_result(world.ports, world.run.id, world.row("tech").seq, result)
    assert world.stored_run().status == "needs_you"
    assert world.stored_run().park_kind == "protected_path"


def test_ac6_the_continue_with_the_files_accepted_closes_the_row() -> None:
    world = a_closing_world(accepted=("backend-api/AGENTS.md",))

    result = ConversationExecutor().execute(context_of(world, "continue", a_git()))

    assert result.status == "done"
    assert result.park is None
    apply_step_result(world.ports, world.run.id, world.row("tech").seq, result)
    assert world.status_of("tech") == "done"


def test_a_continue_without_acceptance_parks_again() -> None:
    world = a_closing_world()

    result = ConversationExecutor().execute(context_of(world, "continue", a_git()))

    assert result.status == "error"


def test_ac7_any_other_record_re_parks_the_conversation_without_a_git_read() -> None:
    world = a_closing_world()
    git = a_git()

    result = ConversationExecutor().execute(context_of(world, "answer", git))

    assert result.status == "checkpoint"
    assert result.park is not None
    assert result.park.kind == "conversation"
    assert git.calls == []


def test_close_hits_without_a_start_sha_is_empty() -> None:
    world = a_closing_world(start_sha=None)
    rows = world.ports.steps.list_for_run(world.run.id)
    turns = world.attempts_of("tech")[1:]

    assert conversation_close.close_hits(a_git(), world.run, rows, world.row("tech"), turns) == ()


def test_close_hits_respells_a_workdir_rows_paths() -> None:
    world = a_closing_world(workdir="repos/member")
    git = FakeGit(
        heads={f"{TREE}/repos/member": ["h1"], TREE: ["h2"]},
        changes={f"{TREE}/repos/member": (Change(path="AGENTS.md", kind="modified"),), TREE: ()},
        statuses={f"{TREE}/repos/member": "", TREE: ""},
    )
    rows = world.ports.steps.list_for_run(world.run.id)

    hits = conversation_close.close_hits(
        git, world.run, rows, world.row("tech"), world.attempts_of("tech")[1:]
    )

    assert hits == ("repos/member/AGENTS.md",)


def test_a_run_without_the_inputs_exempts_nothing() -> None:
    world = a_closing_world()
    run: Run = world.run.model_copy(update={"inputs": {}})
    rows = world.ports.steps.list_for_run(world.run.id)

    hits = conversation_close.close_hits(
        a_git(), run, rows, world.row("tech"), world.attempts_of("tech")[1:]
    )

    assert hits == ("initiatives/demo/epics.yaml", "backend-api/AGENTS.md")
    assert Path(TREE).is_absolute()
