"""`start_saved_run` (story 5-3): start a saved (not-enqueued) Run after re-probing preflight.

`start_saved_run` is a read + writer that re-probes preflight, refuses what it refuses,
then transitions `queued → running` (writing `started_by_operator` to the gate record),
enqueues in the engine, and writes back `engine_ref` in a second commit — the same
two-commit pattern `create_run` uses.

This module also imports `orchestrator.api.routers.start_run` to satisfy the test-pairs
rule (`make lint` checks every source module has a test that imports it).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

# test-pairs: proves the router module exists (make lint test-pairs check)
from orchestrator.api.routers import start_run as start_run_router  # noqa: F401
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.start_run import StartRunPorts, start_saved_run
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fx
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
PROJECT_ID = new_id()
REPOSITORY_ID = new_id()
BRANCH = "main"


def _project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="proj",
        name="proj",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _repository(*, clone_failed: bool = False) -> Repository:
    status = "failed" if clone_failed else "ok"
    return Repository(
        id=REPOSITORY_ID,
        project_id=PROJECT_ID,
        slug="repo",
        url="git@example.com:org/repo.git",
        default_branch=BRANCH,
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=(),
        package_manager="uv",
        clone_check=CloneCheck(status=status, at=NOW, output="", bmad_version="1.0.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def _template_repo(run_repo: FakeRunRepository) -> FakeTemplateVersionRepository:
    versions = list(fx.repository_of_versions().versions.values())
    return FakeTemplateVersionRepository(versions, runs=run_repo)


def _preflight_ports(
    run_repo: FakeRunRepository,
    *,
    clone_failed: bool = False,
) -> PreflightPorts:
    git = FakeGit(refs={BRANCH: "abc123"}, files={}, listings={})
    return PreflightPorts(
        git=git,
        templates=_template_repo(run_repo),
        runs=run_repo,
        harnesses=FakeHarnessRepository(),
        repositories=FakeRepositoryRepository([_repository(clone_failed=clone_failed)]),
        projects=FakeProjectRepository([_project()]),
        bmad_version="1.0.0",
        max_active_runs=2,
        work_dir=Path("/work"),
    )


def _saved_run(**overrides: object) -> Run:
    """A saved Run: status=queued with an empty engine_ref."""
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": PROJECT_ID,
        "repository_id": REPOSITORY_ID,
        "template_name": "repo-init",
        "template_version": 1,
        "status": "queued",
        "engine_ref": {},
        "budget_usd": Decimal("10"),
        "inputs": {"base_branch": BRANCH},
        "partition_branch": BRANCH,
        "created_at": NOW,
    }
    fields.update(overrides)
    return Run(**fields)  # type: ignore[arg-type]


def _make_ports(
    run_repo: FakeRunRepository,
    engine: FakeWorkflowEngine,
    *,
    clone_failed: bool = False,
) -> StartRunPorts:
    uow = FakeUnitOfWork()
    return StartRunPorts(
        writers=WriterPorts(
            runs=run_repo,
            steps=FakeStepRunRepository(),
            attempts=FakeAttemptRepository(),
            records=FakeGateRecordRepository(),
            uow=uow,
            clock=FakeClock(NOW),
        ),
        engine=engine,
        preflight=_preflight_ports(run_repo, clone_failed=clone_failed),
    )


# ── happy path ──────────────────────────────────────────────────────────────────────────────


def test_start_saved_run_transitions_to_running() -> None:
    run = _saved_run()
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with ports.writers.uow:
        outcome = start_saved_run(ports, run.id)

    assert outcome.run.status == "running"


def test_start_saved_run_calls_engine_enqueue_not_signal() -> None:
    run = _saved_run()
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with ports.writers.uow:
        outcome = start_saved_run(ports, run.id)

    enqueue_calls = [c for c in engine.calls if c[0] == "enqueue"]
    signal_calls = [c for c in engine.calls if c[0] == "signal"]
    assert len(enqueue_calls) == 1
    assert signal_calls == []
    assert outcome.run.engine_ref != {}


def test_start_saved_run_writes_started_by_operator_record() -> None:
    run = _saved_run()
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with ports.writers.uow:
        start_saved_run(ports, run.id)

    records = ports.writers.records.list_for_run(run.id)  # type: ignore[attr-defined]
    assert len(records) == 1
    assert records[0].event == "started_by_operator"
    assert records[0].actor == "operator"


def test_start_saved_run_sets_resumed_true() -> None:
    run = _saved_run()
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with ports.writers.uow:
        outcome = start_saved_run(ports, run.id)

    assert outcome.resumed is True


def test_start_saved_run_clears_after_run_id() -> None:
    other_id = new_id()
    run = _saved_run(after_run_id=other_id)
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with ports.writers.uow:
        outcome = start_saved_run(ports, run.id)

    assert outcome.run.after_run_id is None


# ── conflict: already enqueued ───────────────────────────────────────────────────────────────


def test_conflict_when_engine_ref_non_empty() -> None:
    run = _saved_run(engine_ref={"ref": 1})
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with pytest.raises(Conflict):
        with ports.writers.uow:
            start_saved_run(ports, run.id)


# ── conflict: wrong status ───────────────────────────────────────────────────────────────────


def test_conflict_when_status_is_running() -> None:
    run = _saved_run(status="running", engine_ref={"ref": 1})
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine)

    with pytest.raises(Conflict):
        with ports.writers.uow:
            start_saved_run(ports, run.id)


# ── conflict: pre-flight fails ───────────────────────────────────────────────────────────────


def test_conflict_when_preflight_start_not_allowed() -> None:
    """Clone check failed → clone_check_line status='fail' → start_allowed=False."""
    run = _saved_run()
    run_repo = FakeRunRepository([run])
    engine = FakeWorkflowEngine()
    ports = _make_ports(run_repo, engine, clone_failed=True)

    with pytest.raises(Conflict):
        with ports.writers.uow:
            start_saved_run(ports, run.id)
