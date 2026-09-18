"""`signal_run` with `kind="start"` (story 5-3): enqueue a saved Run on Operator request.

AC coverage:
- start on a saved run re-reads Probe, records `event="started_by_operator"`, calls
  engine.enqueue, writes engine_ref, clears after_run_id, returns SignalOutcome(resumed=False)
- start on a non-saved run (engine_ref non-empty) raises 409
- start on status=running raises 409
- Probe fail line on start raises 409 and leaves engine_ref={} unchanged
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.signal_run import SignalPorts, signal_run
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from orchestrator.domain.values import Signal
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)
BUDGET = Decimal("10")
START = Signal(kind="start", payload={})


def project() -> Project:
    return Project(
        id=fixtures.PROJECT.id,
        slug=fixtures.PROJECT.slug,
        name=fixtures.PROJECT.name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository() -> Repository:
    return Repository(
        id=fixtures.REPOSITORY.id,
        project_id=fixtures.PROJECT.id,
        slug=fixtures.REPOSITORY.slug,
        url=fixtures.REPOSITORY.url,
        default_branch=fixtures.REPOSITORY.default_branch,
        install_command=fixtures.REPOSITORY.install_command or "",
        quality_gate_command=fixtures.REPOSITORY.quality_gate_command or "",
        unit_test_command=fixtures.REPOSITORY.unit_test_command or "",
        test_globs=fixtures.REPOSITORY.test_globs,
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version=fixtures.BMAD_VERSION),
        created_at=NOW,
        updated_at=NOW,
    )


def a_saved_run(
    *,
    engine_ref: dict | None = None,
    status: str = "queued",
    after_run_id: UUID | None = None,
) -> Run:
    """A saved run with the inputs dict `_preflight_req_from_run` can reconstruct from."""
    return Run(
        id=new_id(),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="repo-init",
        template_version=1,
        status=status,  # type: ignore[arg-type]
        budget_usd=BUDGET,
        created_at=NOW,
        engine_ref=engine_ref if engine_ref is not None else {},
        inputs={
            "base_branch": fixtures.BASE_BRANCH,
            "harness": "claude",
            "model": None,
        },
        partition_branch=fixtures.INIT_BRANCH,
        after_run_id=after_run_id,
    )


def competing_run() -> Run:
    """A non-terminal run holding the same partition_branch — causes a fail line."""
    return Run(
        id=new_id(),
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        template_name="epic",
        template_version=1,
        status="running",
        budget_usd=BUDGET,
        created_at=NOW,
        inputs={"base_branch": fixtures.INIT_BRANCH, "harness": "claude", "model": None},
        partition_branch=fixtures.INIT_BRANCH,
    )


class StartHarness:
    """Fakes wired for start-signal tests."""

    def __init__(
        self,
        *,
        git: FakeGit,
        runs: list[Run] | None = None,
    ) -> None:
        self.run_repo = FakeRunRepository(runs or [])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.run_repo
        )
        self.engine = FakeWorkflowEngine()
        self.clock = FakeClock(NOW)
        self.uow = FakeUnitOfWork()
        self.records = FakeGateRecordRepository()
        self.steps = FakeStepRunRepository()
        writer_ports = WriterPorts(
            runs=self.run_repo,
            steps=self.steps,
            attempts=FakeAttemptRepository(),
            records=self.records,
            uow=self.uow,
            clock=self.clock,
        )
        # A healthy `claude` harness so the preflight harness-line check passes for
        # saved runs whose inputs carry `harness="claude"` (story 5-3 AC re-read probe).
        claude = Harness(name="claude", version_pin="1.0.0", enabled=True)
        preflight = PreflightPorts(
            git=git,
            templates=self.templates,
            runs=self.run_repo,
            harnesses=FakeHarnessRepository([claude]),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
        )
        self.ports = SignalPorts(
            writers=writer_ports,
            engine=self.engine,
            preflight=preflight,
        )

    def start(self, run: Run) -> object:
        self.run_repo.add(run)
        return signal_run(self.ports, run.id, START)

    def stored_run(self, run: Run) -> Run:
        result = self.run_repo.get(run.id)
        assert result is not None
        return result

    def gate_events(self, run: Run) -> list[str]:
        return [r.event for r in self.records.list_for_run(run.id)]

    def gate_actors(self, run: Run) -> list[str]:
        return [r.actor for r in self.records.list_for_run(run.id)]


# --- start on a saved run: happy path --------------------------------------------------------


def test_start_signal_calls_engine_enqueue() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run()

    harness.start(saved)

    enqueue_calls = [name for name, _ in harness.engine.calls if name == "enqueue"]
    assert len(enqueue_calls) == 1


def test_start_signal_writes_engine_ref() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run()

    harness.start(saved)

    stored = harness.stored_run(saved)
    assert stored.engine_ref != {}


def test_start_signal_clears_after_run_id() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run(after_run_id=None)

    harness.start(saved)

    stored = harness.stored_run(saved)
    assert stored.after_run_id is None


def test_start_signal_records_started_by_operator_event() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run()

    harness.start(saved)

    assert "started_by_operator" in harness.gate_events(saved)


def test_start_signal_records_operator_actor() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run()

    harness.start(saved)

    events = harness.gate_events(saved)
    actors = harness.gate_actors(saved)
    idx = events.index("started_by_operator")
    assert actors[idx] == "operator"


def test_start_signal_returns_resumed_false() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    saved = a_saved_run()

    outcome = harness.start(saved)

    assert outcome.resumed is False  # type: ignore[attr-defined]


# --- start on a non-saved run (engine_ref non-empty) raises 409 ------------------------------


def test_start_signal_refuses_already_enqueued_run() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    already_queued = a_saved_run(engine_ref={"ref": 1}, status="queued")

    with pytest.raises(Conflict):
        harness.start(already_queued)


# --- start on status=running raises 409 ------------------------------------------------------


def test_start_signal_refuses_running_run() -> None:
    harness = StartHarness(git=fixtures.repo_init_git())
    running = a_saved_run(status="running")

    with pytest.raises(Conflict):
        harness.start(running)


# --- Probe fail line: 409 and engine_ref stays {} -------------------------------------------


def test_start_signal_refuses_when_probe_has_fail_line() -> None:
    """When the re-read probe shows a fail line (branch held), start raises 409."""
    other = competing_run()
    harness = StartHarness(
        git=fixtures.repo_init_git(),
        runs=[other],
    )
    saved = a_saved_run()

    with pytest.raises(Conflict):
        harness.start(saved)


def test_start_signal_leaves_engine_ref_empty_on_fail_line() -> None:
    """engine_ref stays {} when the probe refuses the start."""
    other = competing_run()
    harness = StartHarness(
        git=fixtures.repo_init_git(),
        runs=[other],
    )
    saved = a_saved_run()

    with pytest.raises(Conflict):
        harness.start(saved)

    stored = harness.stored_run(saved)
    assert stored.engine_ref == {}
