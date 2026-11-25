"""One project, its hub, an installed fixture package and every port `InitiativePorts` needs.

The templates are this module's own fixtures, never `templates/*.yaml` (hard rule 6). It builds
on `test_create_run_use_case.Harness`, so pre-flight and `create_run` run on the shared fakes.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.initiative import Initiative
from orchestrator.domain.entities.project_package import (
    GateWords,
    PackageDeclaration,
    ProjectPackage,
    SequenceEntry,
)
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.ids import new_id
from tests.unit.application import test_create_run_use_case as base
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.templates.test_conversation_kind import document
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.engine import FakeWorkflowEngine
from tests.unit.fakes.initiatives import FakeInitiativeAdvanceRepository, FakeInitiativeRepository
from tests.unit.fakes.packages import FakeProjectPackageRepository
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.remote_branches import FakeRemoteGit
from tests.unit.fakes.runs import (
    FakeAttemptRepository,
    FakeGateRecordRepository,
    FakeRunRepository,
    FakeStepRunRepository,
)
from tests.unit.initiative_fixtures import a_sequence

FOLDER = "initiatives"
HUB_SHA = fixtures.BASE_SHA
WORK = Path("/work")
SPEC_TEMPLATE = "acme.spec"
SPEC_VERSION = 4
SHIPPED_TEMPLATE = "shipped-build"
SHIPPED_LATEST = 3
INPUTS = """inputs:
  slug: { type: string }
  branch: { type: string }
  first_turn: { type: string }
  initiative_folder: { type: path }
steps:
"""


def spec_yaml(*, first_turn: bool = True) -> str:
    text = document(names=("intake",)).replace("name: talking", "name: spec")
    inputs = INPUTS if first_turn else INPUTS.replace("  first_turn: { type: string }\n", "")
    return text.replace("steps:\n", inputs, 1)


def build_yaml() -> str:
    return "name: shipped-build\nversion: 1\nsteps:\n  - id: b\n    uses: git.merge\n"


def entries() -> tuple[SequenceEntry, ...]:
    return (
        SequenceEntry(
            workflow="spec",
            template=SPEC_TEMPLATE,
            version=SPEC_VERSION,
            type="interactive",
            shown_as="workflow",
            steps=(),
        ),
        SequenceEntry(
            workflow="build",
            template=SHIPPED_TEMPLATE,
            version=None,
            type="auto",
            shown_as="step",
            steps=(),
        ),
    )


class InitiativeWorld:
    """The wiring of `providers_initiatives.initiative_ports`, over the shared fakes."""

    def __init__(self, *, first_turn: bool = True, git: FakeRemoteGit | None = None) -> None:
        self.git = git or FakeRemoteGit(refs={"main": HUB_SHA})
        self.harness = base.Harness(git=self.git)
        self.runs: FakeRunRepository = self.harness.runs
        self.templates = self.harness.templates
        self.templates.add(
            TemplateVersion(
                name=SPEC_TEMPLATE,
                version=SPEC_VERSION,
                yaml=spec_yaml(first_turn=first_turn),
                hash="h4",
                source="package",
            )
        )
        for version in range(1, SHIPPED_LATEST + 1):
            self.templates.add(
                TemplateVersion(
                    name=SHIPPED_TEMPLATE,
                    version=version,
                    yaml=build_yaml(),
                    hash=f"b{version}",
                    source="shipped",
                )
            )
        self.project = base.project().model_copy(
            update={
                "default_budget_usd": Decimal("7.50"),
                "default_harness": "claude",
                "default_model": "sonnet",
            }
        )
        self.hub = base.repository().model_copy(update={"initiative_folder": FOLDER})
        self.projects = FakeProjectRepository([self.project])
        self.repositories = FakeRepositoryRepository([self.hub])
        preflight = replace(
            self.harness.ports.preflight,
            projects=self.projects,
            repositories=self.repositories,
        )
        self.create_ports = replace(
            self.harness.ports, preflight=preflight, initiative_runs=self.runs
        )
        self.packages = FakeProjectPackageRepository()
        self.package = ProjectPackage(
            id=new_id(),
            project_id=self.project.id,
            repository_id=self.hub.id,
            path="pkg",
            ref="main",
            sha="c" * 40,
            name="acme",
            declaration=PackageDeclaration(
                name="acme",
                sequence=entries(),
                gate=GateWords(pass_words=("pass",), fail_words=("fail",), owners_key="owners"),
                status_map={"final": "done"},
            ),
            installed_at=self.harness.clock.now(),
        )
        self.packages.put(self.package)
        self.initiatives = FakeInitiativeRepository()
        self.advances = FakeInitiativeAdvanceRepository()
        self.uow: FakeUnitOfWork = self.harness.uow
        self.signal_uow = FakeUnitOfWork()
        self.engine = FakeWorkflowEngine(clock=FakeClock(), uow=self.signal_uow)
        self.signals = SignalPorts(
            writers=WriterPorts(
                runs=self.runs,
                steps=FakeStepRunRepository(),
                attempts=FakeAttemptRepository(),
                records=FakeGateRecordRepository(),
                uow=self.signal_uow,
                clock=FakeClock(),
            ),
            engine=self.engine,
        )

    @property
    def ports(self) -> InitiativePorts:
        return InitiativePorts(
            initiatives=self.initiatives,
            advances=self.advances,
            projects=self.projects,
            repositories=self.repositories,
            packages=self.packages,
            templates=self.templates,
            runs=self.runs,
            git=self.git,
            branches=self.git,
            create_run=self.create_ports,
            signals=self.signals,
            uow=self.uow,
            clock=self.harness.clock,
            work_dir=WORK,
        )

    @property
    def base_dir(self) -> Path:
        return WORK / self.project.slug / self.hub.slug / "base"

    def seed(self, initiative: Initiative, *runs: Run) -> Initiative:
        self.initiatives.add(initiative)
        for run in runs:
            self.runs.add(run)
        return initiative

    def initiative(self, **overrides: Any) -> Initiative:
        values: dict[str, Any] = {
            "id": new_id(),
            "project_id": self.project.id,
            "repository_id": self.hub.id,
            "slug": "snake-v3",
            "name": "Snake v3",
            "first_message": "hello",
            "sequence": a_sequence("acme"),
            "created_at": self.harness.clock.now(),
        }
        values.update(overrides)
        return Initiative(**values)
