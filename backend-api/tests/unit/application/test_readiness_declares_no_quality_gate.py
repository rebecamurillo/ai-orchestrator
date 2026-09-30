"""The readiness fixture declares no commands — and so its Run reaches its agent row.

Readiness proves the harness, not the repository (SPEC CAP-8). The seed used to give the
readiness Repository `quality_gate_command="sh check.sh"`, which
`fixtures/readiness-repo/check.sh` only satisfies once `HELLO.md` exists — which is the
very thing the readiness Story is dispatched to do. The epic Template ran that command
before any agent had touched the tree with `on_fail: fail`, so every readiness Run ended
`failed` on an early row, no agent was ever dispatched, and no harness could reach
`enabled`. What was wrong is asking a harness-readiness fixture to be green before the
work it exists to do — so the fixture declares no command at all, every shell row skips
naming the field it asked for, and the walk reaches the agent row.

The plan half runs against the *shipped* file a default instance's `READINESS_TEMPLATE`
names, at the exact pin `harness_readiness.start` would write into the Run (the latest
stored version of that name — `latest_version`), because this is a claim about what
readiness really executes. The name is read off `Settings`' own field default rather than
retyped (Operator decision 2026-09-30: no template name hardcoded in product code).

The shipped Templates evolve freely — steps are added, renamed
and re-parameterised — so nothing here names a step, counts a row or pins a reason to a
path: every assertion is a property that must hold for *any* epic Template a readiness
Run may plan. Row-by-row planner coverage lives with the frozen exemplars in
`templates/test_plan_shipped.py`.

Every fact here is read from the product: the Repository comes out of
`seed_readiness_project`, its snapshot out of `preflight._run_inputs`, the Template out of
the same `seed_shipped` start-up runs, and the rows out of `plan_run`. Nothing is retyped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import Plan, names_a_field
from orchestrator.application.use_cases.harness_readiness import (
    READINESS_BASE_BRANCH,
    READINESS_REPOSITORY_SLUG,
    READINESS_SPEC_FOLDER,
    READINESS_STORY_ID,
)
from orchestrator.application.use_cases.harness_readiness_seed import seed_readiness_project
from orchestrator.application.use_cases.plan_run import resolve_tree
from orchestrator.application.use_cases.preflight import _run_inputs
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.application.use_cases.templates import (
    TemplatePorts,
    latest_version,
    seed_shipped,
)
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository
from tests.unit.fakes.templates import FakeTemplateVersionRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)
WORK_DIR = Path("/work")
BMAD_VERSION = "6.11.0"

#: What `harness_readiness.start` names the branch, and the head the remote holds for it.
BRANCH = "readiness/claude/2026-03-04"
BRANCH_SHA = "b" * 40
BASE_SHA = "a" * 40

#: The shipped Templates live beside the repository root, not with the exemplar fixtures.
SHIPPED_DIR = fixtures.REPO_ROOT / "templates"

#: The fixture's one Story, read off disk so the plan expands what the image really ships.
STORIES_YAML = (
    fixtures.REPO_ROOT / "fixtures" / "readiness-repo" / READINESS_SPEC_FOLDER / "stories.yaml"
).read_text()


def seeded() -> tuple[Project, Repository]:
    """The built-in `readiness` Project and its Repository, exactly as start-up writes them."""
    uow = FakeUnitOfWork()
    ports = ProjectPorts(
        uow=uow,
        projects=FakeProjectRepository(),
        crypto=FakeCrypto(),
        clock=FakeClock(NOW),
        repositories=FakeRepositoryRepository(),
        git=None,
    )
    with uow:
        project = seed_readiness_project(ports, work_dir=WORK_DIR, bmad_version=BMAD_VERSION)
    assert ports.repositories is not None
    repository = next(
        stored
        for stored in ports.repositories.list_by_project(project.id)
        if stored.slug == READINESS_REPOSITORY_SLUG
    )
    return project, repository


@pytest.fixture
def repository() -> Repository:
    return seeded()[1]


@pytest.fixture
def readiness_plan() -> Plan:
    """The shipped Template readiness pins, planned over the seeded Repository, through the
    product's own snapshot."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    seed_shipped(
        TemplatePorts(uow=uow, templates=templates, clock=FakeClock(NOW)),
        load_shipped_templates(SHIPPED_DIR),
    )
    name = str(Settings.model_fields["readiness_template"].default)
    tree = resolve_tree(templates, TemplateRef(name=name, version=latest_version(templates, name)))
    project, stored = seeded()
    run_inputs = _run_inputs(
        PreflightRequest(
            base_branch=READINESS_BASE_BRANCH,
            inputs={"branch": BRANCH, "spec_folder": READINESS_SPEC_FOLDER},
            harness="claude",
        ),
        project,
        stored,
    )
    assert run_inputs is not None
    git = FakeGit(
        refs={READINESS_BASE_BRANCH: BASE_SHA, BRANCH: BRANCH_SHA},
        files={(BRANCH_SHA, f"{READINESS_SPEC_FOLDER}/stories.yaml"): STORIES_YAML},
        listings={},
    )
    return plan_run(
        tree,
        run_inputs,
        git=git,
        base_dir=WORK_DIR / "readiness" / READINESS_REPOSITORY_SLUG / "base",
        bmad_version=BMAD_VERSION,
    )


# ── the seed ─────────────────────────────────────────────────────────────────────────────


def test_the_seeded_readiness_repository_declares_no_quality_gate(
    repository: Repository,
) -> None:
    assert repository.quality_gate_command == ""


def test_the_seeded_readiness_repository_reads_as_verify_skipped(
    repository: Repository,
) -> None:
    """The representation the UX already renders as `— none declared` (FR-3)."""
    assert repository.verify_skipped is True


def test_the_seeded_repository_snapshots_as_no_command_rather_than_an_empty_one() -> None:
    """`dto.RepositorySnapshot`'s rule: `None` is what a substitution can tell apart."""
    project, stored = seeded()
    run_inputs = _run_inputs(PreflightRequest(base_branch=READINESS_BASE_BRANCH), project, stored)

    assert run_inputs is not None
    assert run_inputs.repository.quality_gate_command is None


# ── the plan ─────────────────────────────────────────────────────────────────────────────


def test_every_shell_row_is_skipped_naming_the_command_it_asked_for(
    readiness_plan: Plan,
) -> None:
    """The fixture Repository states no command at all, so whatever shell rows the shipped
    Template declares, each one skips — and each reason names its own field (FR-8), which
    is what `_verify_line` reads as "nothing to prove" rather than a readiness failure."""
    shell_rows = [entry for entry in readiness_plan.rows if entry.kind == "shell"]

    for entry in shell_rows:
        assert entry.status == "skipped", entry.path
        assert entry.reason is not None and names_a_field(entry.reason), entry.path


def test_the_readiness_run_reaches_its_agent_row(readiness_plan: Plan) -> None:
    """The whole point: nothing before the first dispatch is failed or in the way, so the
    walk gets as far as handing the readiness Story to the harness.

    Updated 2026-09-17 (story 4-4): spec-gate agent step inserted after baseline.
    Filtering by story_id restores the invariant: the test asserts that the readiness
    story's agent dispatch is reachable and planned, regardless of epic-level steps before it.
    """
    agent_rows = [entry for entry in readiness_plan.rows if entry.kind == "agent"]

    assert agent_rows, "the shipped readiness Template dispatches no agent at all"
    story_rows = [e for e in agent_rows if e.story_id == READINESS_STORY_ID]
    assert story_rows, "no agent row found for the readiness story"
    first = story_rows[0]
    assert first.status == "planned"
    before = [entry for entry in readiness_plan.rows if entry.seq < first.seq]
    assert all(entry.status in ("planned", "skipped") for entry in before), [
        (entry.path, entry.status) for entry in before
    ]


def test_no_row_of_the_readiness_plan_is_born_failed(readiness_plan: Plan) -> None:
    assert {entry.status for entry in readiness_plan.rows} <= {"planned", "skipped"}
