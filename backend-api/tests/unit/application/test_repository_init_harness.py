"""`init_repository`'s `harness` override (Operator decision, 2026-09-16): the exemplar
initialisation Template gained an `agent` row, and a stack that can only dispatch a seeded
test harness (ORCH_TEST_MODE) needs the init action to accept the name. The override is
handed to `create_run` unchanged — including its pre-flight.

Reuses `test_repository_init.py`'s fixtures; its own `Harness` wiring pins an empty
harness table, so this file wires the one difference — a `harness_registry` entry for
the named harness with scripted probe results (Operator decision 2026-09-16: pre-flight
now uses live probe via harness_registry, not the DB enabled flag)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.dto import DEFAULT_HARNESS
from orchestrator.application.use_cases.create_run import CreateRunPorts, CreateRunResult
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.repositories import (
    InitRepositoryPorts,
    init_repository,
)
from orchestrator.domain.entities.harness import Harness
from orchestrator.domain.ports.harness import ProbeResult
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_repository_init import TEMPLATE_NAME, project, repository
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harness import FakeHarness
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class World:
    """`test_repository_init.py::Harness`, with the harness table this file needs."""

    def __init__(self) -> None:
        self.runs = FakeRunRepository([])
        self.templates = FakeTemplateVersionRepository(
            list(fixtures.repository_of_versions().versions.values()), runs=self.runs
        )
        self.uow = FakeUnitOfWork()
        # Operator decision 2026-09-16: harness check now uses live probe via harness_registry.
        # Two ProbeResult entries required: one consumed by harness_probe_line (pre-flight),
        # one consumed by create_run's inline probe block.
        _ok_probe = ProbeResult(ok=True, failing_reason=None, version="test", models=[])
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(
                [Harness(name="fake", enabled=True, version_pin="test")]
            ),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
            harness_registry={
                "fake": FakeHarness(
                    name="fake",
                    probe_results=[_ok_probe, _ok_probe],
                )
            },
        )
        self.ports = InitRepositoryPorts(
            create_run=CreateRunPorts(
                preflight=preflight,
                engine=FakeWorkflowEngine(),
                steps=FakeStepRunRepository(),
                uow=self.uow,
                clock=FakeClock(NOW),
            ),
            template_name=TEMPLATE_NAME,
        )

    def init(self, harness: str | None) -> CreateRunResult:
        with self.uow:
            return init_repository(self.ports, fixtures.REPOSITORY.id, harness)


def test_a_named_harness_reaches_the_runs_inputs() -> None:
    # Operator decision 2026-09-16: probe-based semantics replace the enabled flag;
    # World wires harness_registry so create_run succeeds and inputs["harness"] is stored.
    world = World()

    result = world.init("fake")

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.inputs["harness"] == "fake"


def test_no_harness_still_dispatches_the_default() -> None:
    world = World()

    result = world.init(None)

    stored = world.runs.get(result.run.id)
    assert stored is not None
    assert stored.inputs["harness"] == DEFAULT_HARNESS
