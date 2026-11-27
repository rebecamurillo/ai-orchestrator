"""`create_run` plans the template version it is given and refuses one that is gone
(epic 3, story 3, 2026-11-23; SPEC CAP-3, FR-9; AD-15 "Versions").

The fixture template `frozen-demo` is test-owned text derived from `plan_fixtures.TEXTS`;
version 2 drops the `link` step so the two versions plan different rows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from orchestrator.application.templates.plan_model import PlanError
from orchestrator.application.use_cases.create_run import (
    CreateRunPorts,
    CreateRunRequest,
    CreateRunResult,
    create_run,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_use_case import (
    BUDGET,
    NOW,
    project,
    repository,
)
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.runs import FakeRunRepository, FakeStepRunRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NAME = "frozen-demo"
MISSING_VERSION = 9
V1_ROWS = 8

_V1 = fixtures.TEXTS["repo-init"].replace("name: repo-init", f"name: {NAME}", 1)
_V2 = re.sub(r"  - id: link\n(?:    .*\n)+", "", _V1.replace("version: 1", "version: 2", 1))


def frozen_demo_store(runs: FakeRunRepository) -> FakeTemplateVersionRepository:
    return FakeTemplateVersionRepository(
        [
            TemplateVersion(name=NAME, version=1, yaml=_V1, hash="v1"),
            TemplateVersion(name=NAME, version=2, yaml=_V2, hash="v2"),
        ],
        runs=runs,
    )


class Harness:
    def __init__(self) -> None:
        self.runs = FakeRunRepository([])
        self.steps = FakeStepRunRepository()
        self.engine = FakeWorkflowEngine()
        self.uow = FakeUnitOfWork()
        preflight = PreflightPorts(
            git=fixtures.repo_init_git(),
            templates=frozen_demo_store(self.runs),
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=FakeRepositoryRepository([repository()]),
            projects=FakeProjectRepository([project()]),
            bmad_version=fixtures.BMAD_VERSION,
            max_active_runs=2,
            work_dir=Path("/work"),
        )
        self.ports = CreateRunPorts(
            preflight=preflight,
            engine=self.engine,
            steps=self.steps,
            uow=self.uow,
            clock=FakeClock(NOW),
        )

    def create(self, version: int) -> CreateRunResult:
        request = CreateRunRequest(
            template_name=NAME,
            template_version=version,
            project_id=fixtures.PROJECT.id,
            repository_id=fixtures.REPOSITORY.id,
            base_branch=fixtures.BASE_BRANCH,
            budget_usd=BUDGET,
        )
        with self.uow:
            return create_run(self.ports, request)


def test_the_fixture_versions_plan_different_rows() -> None:
    assert "id: link" in _V1
    assert "id: link" not in _V2
    assert "version: 2" in _V2


def test_a_run_at_version_1_plans_version_1_even_though_version_2_exists() -> None:
    harness = Harness()

    result = harness.create(1)

    stored = harness.runs.get(result.run.id)
    assert stored is not None
    assert stored.template_version == 1
    assert stored.pinned_versions == (TemplateRef(name=NAME, version=1),)
    rows = harness.steps.list_for_run(result.run.id)
    assert len(rows) == V1_ROWS
    assert "link" in [row.path for row in rows]


def test_a_run_at_version_2_plans_version_2() -> None:
    harness = Harness()

    result = harness.create(2)

    rows = harness.steps.list_for_run(result.run.id)
    assert len(rows) == V1_ROWS - 1
    assert "link" not in [row.path for row in rows]


def test_a_version_that_is_not_stored_is_refused_before_anything_persists() -> None:
    harness = Harness()

    with pytest.raises(PlanError) as refused:
        harness.create(MISSING_VERSION)

    assert refused.value.template == NAME
    assert refused.value.version == MISSING_VERSION
    assert refused.value.item == f"{NAME}@{MISSING_VERSION}"
    assert harness.runs.runs == {}
    assert harness.steps.steps == {}
    assert harness.engine.calls == []
