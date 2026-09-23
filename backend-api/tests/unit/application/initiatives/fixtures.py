"""The scripted world a dispatch test runs in (multi-repo initiative S6, 2026-09-23).

**The Templates here are the tests' own, not the shipped ones.** Hard rule 6: "No test, unit
or e2e, may pin shipped template content … cover template behaviour on fixture copies the
test owns." So this module writes three minimal files — one epic-shaped, one merge-shaped,
one go-live-shaped — under names the shipped files do not use. That is also what proves the
property the story asks for: the dispatch instantiates whatever the request names, so a
dispatch of `epic-fixture` works exactly as a dispatch of `epic` does.

**One `FakeGit` serves every repository**, because that fake keys its `refs` by branch name
alone. The fixture therefore gives each repository a branch namespace of its own
(`develop-web`, `develop-api`) and shares only `main`, which is what a real multi-repository
project looks like anyway.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from orchestrator.application.initiatives.model import (
    DispatchResult,
    InitiativeRequest,
    MemberRun,
)
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.dispatch_initiative import (
    DispatchPorts,
    dispatch_initiative,
)
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.template import TemplateVersion
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
BMAD_VERSION = "6.11.0"
WORK_DIR = Path("/work")
BUDGET = Decimal("25")

PROJECT_ID = UUID("01960000-0000-7000-8000-0000000000a0")
HUB_ID = UUID("01960000-0000-7000-8000-0000000000a1")
WEB_ID = UUID("01960000-0000-7000-8000-0000000000a2")
API_ID = UUID("01960000-0000-7000-8000-0000000000a3")

MAIN = "main"
MAIN_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
WEB_BRANCH = "develop-web"
API_BRANCH = "develop-api"

INITIATIVE_FOLDER = "_bmad-output/initiatives/q4"
SLUG = "q4"
EPICS_PATH = f"{INITIATIVE_FOLDER}/epics.yaml"

WEB_SPEC = "specs/web-1"
API_SPEC = "specs/api-1"

#: What the per-Run pre-flight reads to answer its `SPEC.md` and `method version` lines.
SPEC_MD = "# The spec\n\nWhat this epic does.\n"
MANIFEST_PATH = "_bmad/_config/manifest.yaml"
MANIFEST = f"installation:\n  version: {BMAD_VERSION}\n"

#: The Template names this suite dispatches. Deliberately not the shipped ones.
EPIC_TEMPLATE = "epic-fixture"
MERGE_TEMPLATE = "merge-fixture"
GOLIVE_TEMPLATE = "golive-fixture"

EPIC_YAML = """
name: epic-fixture
version: {version}
description: a fixture epic, owned by this test
inputs:
  project:     {{ type: project,    required: true }}
  repository:  {{ type: repository, required: true }}
  base_branch: {{ type: string,     required: true }}
  branch:      {{ type: string,     required: true }}
  spec_folder: {{ type: path,       required: true }}
  epic:        {{ type: item,       required: false }}
  harness:     {{ type: enum, values: [claude, codex, local], default: claude }}
  model:       {{ type: string,     required: false }}
  done_checkpoint: {{ type: string, required: false }}
steps:
  - id: checkout
    uses: git.worktree
    with: {{ base: "{{{{base_branch}}}}", branch: "{{{{branch}}}}" }}
    gate: deterministic
  - id: push
    uses: git.push
    with: {{ branch: "{{{{branch}}}}" }}
    gate: deterministic
  - id: done-checkpoint
    uses: checkpoint
    with: {{ when: "{{{{done_checkpoint}}}}" }}
    gate: human
"""

MERGE_YAML = """
name: merge-fixture
version: 1
description: a fixture merge, owned by this test
inputs:
  project:        { type: project,    required: true }
  repository:     { type: repository, required: true }
  base_branch:    { type: string,     required: true }
  develop_branch: { type: string,     required: true }
  from_branch:    { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{develop_branch}}", mode: attach }
    gate: deterministic
  - id: merge
    uses: git.merge
    with: { from: "{{from_branch}}" }
    gate: deterministic
  - id: push
    uses: git.push
    with: { branch: "{{develop_branch}}" }
    gate: deterministic
"""

GOLIVE_YAML = """
name: golive-fixture
version: 1
description: a fixture go-live, owned by this test
inputs:
  project:    { type: project,    required: true }
  repository: { type: repository, required: true }
  holds:      { type: string,     required: false }
steps:
  - id: go-live
    uses: checkpoint
    gate: human
"""

#: Two repositories, one dependency, one `block_merge` stop and one `go_live` stop.
EPICS_YAML = f"""
- id: web-1
  title: The web epic
  repo: web
  branch: {WEB_BRANCH}
  spec_folder: {WEB_SPEC}
  checkpoint: go_live
- id: api-1
  title: The api epic
  repo: api
  branch: {API_BRANCH}
  spec_folder: {API_SPEC}
  depends_on: [web-1]
  done_checkpoint: true
"""


def project() -> Project:
    return Project(
        id=PROJECT_ID,
        slug="my-project",
        name="My Project",
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=NOW,
        updated_at=NOW,
    )


def repository(repository_id: UUID, slug: str) -> Repository:
    return Repository(
        id=repository_id,
        project_id=PROJECT_ID,
        slug=slug,
        url=f"https://github.com/org/{slug}.git",
        default_branch=MAIN,
        install_command="uv sync",
        quality_gate_command="make check",
        unit_test_command="pytest -q",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version=BMAD_VERSION),
        created_at=NOW,
        updated_at=NOW,
    )


def repositories() -> list[Repository]:
    """The hub and the two member repositories, in the order a Project lists them."""
    return [
        repository(HUB_ID, "hub"),
        repository(WEB_ID, "web"),
        repository(API_ID, "api"),
    ]


def templates(*, epic_versions: tuple[int, ...] = (1,)) -> FakeTemplateVersionRepository:
    """The three fixture Templates. `epic_versions` stores more than one, so a test can
    prove the dispatch resolves the **latest** rather than a hardcoded number."""
    stored = [
        TemplateVersion(
            name=EPIC_TEMPLATE, version=number, yaml=EPIC_YAML.format(version=number), hash="s"
        )
        for number in epic_versions
    ]
    stored += [
        TemplateVersion(name=MERGE_TEMPLATE, version=1, yaml=MERGE_YAML, hash="s"),
        TemplateVersion(name=GOLIVE_TEMPLATE, version=1, yaml=GOLIVE_YAML, hash="s"),
    ]
    return FakeTemplateVersionRepository(stored)


def git(
    *,
    epics: str | None = EPICS_YAML,
    refs: dict[str, str] | None = None,
    specs: tuple[str, ...] = (WEB_SPEC, API_SPEC),
) -> FakeGit:
    """A remote holding `main`, the `epics.yaml` on it, and each epic's spec folder."""
    files: dict[tuple[str, str], str] = {(MAIN_SHA, MANIFEST_PATH): MANIFEST}
    if epics is not None:
        files[(MAIN_SHA, EPICS_PATH)] = epics
    for folder in specs:
        files[(MAIN_SHA, f"{folder}/SPEC.md")] = SPEC_MD
    listings = {(MAIN_SHA, folder): [f"{folder}/SPEC.md"] for folder in specs}
    return FakeGit(refs=dict(refs or {MAIN: MAIN_SHA}), files=files, listings=listings)


class Harness:
    """One dispatch's whole world: the fakes, the ports, and the request."""

    def __init__(  # noqa: PLR0913 — one keyword per scripted fact, each optional
        self,
        *,
        epics: str | None = EPICS_YAML,
        refs: dict[str, str] | None = None,
        specs: tuple[str, ...] = (WEB_SPEC, API_SPEC),
        stored: list[Repository] | None = None,
        epic_versions: tuple[int, ...] = (1,),
        max_active_runs: int = 2,
    ) -> None:
        self.git = git(epics=epics, refs=refs, specs=specs)
        self.runs = FakeRunRepository()
        self.steps = FakeStepRunRepository()
        self.templates = templates(epic_versions=epic_versions)
        self.uow = FakeUnitOfWork()
        # the writer ports own a second unit of work, exactly as production does: the
        # provider opens one session for the creation path and a second for the short
        # transactions `enqueue_saved_run` opens and closes per Run
        self.writer_uow = FakeUnitOfWork()
        self.clock = FakeClock(NOW)
        self.engine = FakeWorkflowEngine(uow=self.uow)
        self.repositories = FakeRepositoryRepository(
            stored if stored is not None else repositories()
        )
        self.preflight = PreflightPorts(
            git=self.git,
            templates=self.templates,
            runs=self.runs,
            harnesses=FakeHarnessRepository(),
            repositories=self.repositories,
            projects=FakeProjectRepository([project()]),
            bmad_version=BMAD_VERSION,
            max_active_runs=max_active_runs,
            work_dir=WORK_DIR,
        )
        self.create = CreateRunPorts(
            preflight=self.preflight,
            engine=self.engine,
            steps=self.steps,
            uow=self.uow,
            clock=self.clock,
        )
        self.writers = WriterPorts(
            runs=self.runs,
            steps=self.steps,
            attempts=FakeAttemptRepository(),
            records=FakeGateRecordRepository(),
            uow=self.writer_uow,
            clock=self.clock,
            engine=self.engine,
        )
        self.ports = DispatchPorts(create=self.create, writers=self.writers)

    def dispatch(self, req: InitiativeRequest) -> DispatchResult:
        """Run the dispatch inside the transaction its provider would have opened."""
        with self.uow:
            return dispatch_initiative(self.ports, req)

    def run_of(self, member: MemberRun) -> Run:
        """The stored Run one reported member names."""
        stored = self.runs.get(member.run_id)
        assert stored is not None
        return stored


def request(**overrides: object) -> InitiativeRequest:
    """The request every test starts from; keyword overrides change one field at a time."""
    fields: dict[str, object] = {
        "project_id": PROJECT_ID,
        "repository_id": HUB_ID,
        "base_branch": MAIN,
        "initiative_folder": INITIATIVE_FOLDER,
        "epic_template": EPIC_TEMPLATE,
        "merge_template": MERGE_TEMPLATE,
        "golive_template": GOLIVE_TEMPLATE,
        "budget_usd_per_epic": BUDGET,
    }
    fields.update(overrides)
    return InitiativeRequest(**fields)  # type: ignore[arg-type]
