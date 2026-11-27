"""`InitiativeReadPorts` on the shared fakes, and the fixture sequence of story 4 (AD-36).

The sequence is this module's own (hard rule 6): `spec` (interactive, a conversation step and
the gate), `merge` (interactive, `shown_as: step`), `build` (auto), optionally `deploy` (auto).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.domain.entities.attempt import Attempt
from orchestrator.domain.entities.gate_record import GateRecord
from orchestrator.domain.entities.initiative import FrozenSequence, FrozenWorkflow, Initiative
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.project_package import GateWords, StepDecl
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.git_history import FakeGitHistory
from tests.unit.fakes.initiatives import FakeInitiativeAdvanceRepository, FakeInitiativeRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.fakes.workspace import FakeWorkspace
from tests.unit.initiative_fixtures import AT

NOW = AT + timedelta(days=60)
WORKTREE = "/work/wt/spec-snake"
FOLDER = "initiatives"
STATUS_MAP = {"done": "done", "running": "running", "blocked": "waiting for her"}
GATE = GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners")


def sequence(*, deploy: bool = False) -> FrozenSequence:
    talk = StepDecl(
        id="intake",
        kind="conversation",
        skill="s",
        persona="analyst",
        file="PRD.md",
        writes=("SPEC.md",),
    )
    gate = StepDecl(id="gate", kind="automatic", skill=None, persona=None, file=None, writes=())
    workflows = [
        FrozenWorkflow(
            workflow="spec",
            template="p/spec",
            version=2,
            type="interactive",
            shown_as="workflow",
            steps=(talk, gate),
        ),
        FrozenWorkflow(
            workflow="merge",
            template="p/merge",
            version=1,
            type="interactive",
            shown_as="step",
            steps=(),
        ),
        FrozenWorkflow(
            workflow="build",
            template="p/build",
            version=1,
            type="auto",
            shown_as="workflow",
            steps=(),
        ),
    ]
    if deploy:
        workflows.append(
            FrozenWorkflow(
                workflow="deploy",
                template="p/deploy",
                version=1,
                type="auto",
                shown_as="workflow",
                steps=(),
            )
        )
    return FrozenSequence(
        package="p", sha="abc123", workflows=tuple(workflows), gate=GATE, status_map=STATUS_MAP
    )


def a_project(name: str = "Acme", slug: str = "acme") -> Project:
    return Project(
        id=new_id(),
        slug=slug,
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=AT,
        updated_at=AT,
    )


def a_repository(project_id: UUID, slug: str = "hub") -> Repository:
    return Repository(
        id=new_id(),
        project_id=project_id,
        slug=slug,
        url=f"https://example.invalid/{slug}.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=AT, output="", bmad_version="6.11.0"),
        created_at=AT,
        updated_at=AT,
        initiative_folder=FOLDER,
    )


class ReadWorld:
    """Two stores' worth of fakes behind one `InitiativeReadPorts`."""

    def __init__(self, *, git: FakeGit | None = None) -> None:
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.initiatives = FakeInitiativeRepository()
        self.advances = FakeInitiativeAdvanceRepository()
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.attempts = FakeAttemptRepository()
        self.git = git or FakeGit()
        self.records = FakeGateRecordRepository()
        self.history = FakeGitHistory()
        self.clock = FakeClock(NOW)
        self.files: dict[str, str] = {}
        self.project = a_project()
        self.hub = a_repository(self.project.id)
        self.projects.add(self.project)
        self.repositories.add(self.hub)

    def workspace(self, path: str | None) -> FakeWorkspace:
        return FakeWorkspace(path, dict(self.files))

    @property
    def ports(self) -> InitiativeReadPorts:
        return InitiativeReadPorts(
            initiatives=self.initiatives,
            advances=self.advances,
            projects=self.projects,
            repositories=self.repositories,
            runs=self.runs,
            initiative_runs=self.runs,
            steps=self.steps,
            attempts=self.attempts,
            git=self.git,
            workspace=self.workspace,
            clock=self.clock,
            records=self.records,
            history=self.history,
        )

    def initiative(self, **overrides: Any) -> Initiative:
        values: dict[str, Any] = {
            "id": new_id(),
            "project_id": self.project.id,
            "repository_id": self.hub.id,
            "slug": "snake",
            "name": "Snake",
            "first_message": "make a snake game",
            "sequence": sequence(),
            "created_at": AT,
        }
        values.update(overrides)
        initiative = Initiative(**values)
        self.initiatives.add(initiative)
        return initiative

    def run(
        self, initiative: Initiative, *, position: int = 0, minutes: int = 0, **overrides: Any
    ) -> Run:
        values: dict[str, Any] = {
            "id": new_id(),
            "project_id": initiative.project_id,
            "repository_id": initiative.repository_id,
            "template_name": "p/spec",
            "template_version": 2,
            "inputs": {},
            "status": "running",
            "budget_usd": None,
            "initiative_id": initiative.id,
            "initiative_round": 1,
            "initiative_position": position,
            "created_at": AT + timedelta(minutes=minutes),
        }
        values.update(overrides)
        run = Run(**values)
        self.runs.add(run)
        return run

    def row(self, run: Run, seq: int, **overrides: Any) -> StepRun:
        values: dict[str, Any] = {
            "id": new_id(),
            "run_id": run.id,
            "seq": seq,
            "path": f"steps[{seq}]",
            "label": f"row {seq}",
            "kind": "conversation",
            "gate": "human",
            "status": "planned",
            "with_resolved": {"step": "intake"},
        }
        values.update(overrides)
        row = StepRun(**values)
        self.steps.add_many([row])
        return row

    def turn(self, row: StepRun, n: int, **overrides: Any) -> Attempt:
        values: dict[str, Any] = {
            "id": new_id(),
            "run_id": row.run_id,
            "step_run_id": row.id,
            "n": n,
            "status": "done",
            "role": "session",
            "message": f"message {n}",
            "reply": f"reply {n}",
        }
        values.update(overrides)
        attempt = Attempt(**values)
        self.attempts.add(attempt)
        return attempt

    def session_start(self, run: Run, row: StepRun, minutes: int, **payload: Any) -> GateRecord:
        record = GateRecord(
            id=new_id(),
            run_id=run.id,
            at=AT + timedelta(minutes=minutes),
            path=row.path,
            event="session_start",
            actor="operator",
            payload={"scope": "step", **payload},
        )
        self.records.add(record)
        return record

    def parked_spec(self, initiative: Initiative, turns: int = 2, **overrides: Any) -> Run:
        """A spec Run parked on its conversation row with `turns` ended session attempts."""
        row_id = new_id()
        run = self.run(
            initiative,
            status="needs_you",
            park_kind="conversation",
            park_path="steps[1]",
            park_seq=3,
            **overrides,
        )
        row = self.row(run, 1, id=row_id, status="checkpoint")
        for n in range(1, turns + 1):
            self.turn(row, n)
        return run


def at(days: int) -> datetime:
    return datetime(2026, 11, 24, 9, 0, tzinfo=UTC) - timedelta(days=days)
