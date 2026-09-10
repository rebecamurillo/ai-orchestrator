"""The readiness fixture declares no quality gate — and so its Run reaches its agent row.

Readiness proves the harness, not the repository (SPEC CAP-8). The seed used to give the
readiness Repository `quality_gate_command="sh check.sh"`, which
`fixtures/readiness-repo/check.sh` only satisfies once `HELLO.md` exists — which is the
very thing the readiness Story is dispatched to do. `epic@1`'s `baseline` row runs that
command before any agent has touched the tree and carries `on_fail: fail`, so every
readiness Run ended `failed` on its second row, no agent was ever dispatched, and no
harness could reach `enabled` — which left every Run naming a harness failing pre-flight's
`harness_line` with `disabled: {check}`.

`baseline` is not what was wrong: a red gate at baseline is how the Operator learns the
repository was already broken before an agent touched it, and these tests assert that
`epic@1` still declares `on_fail: fail` there. What was wrong is asking a
harness-readiness fixture to be green before the work it exists to do. So the fixture
declares no gate, the planner skips `baseline` and every `verify` as
`skipped · no quality_gate_command`, and the walk reaches the `build` row.

Every fact here is read from the product: the Repository comes out of
`seed_readiness_project`, its snapshot out of `preflight._run_inputs`, and the rows out of
`plan_run` over the shipped `templates/epic.yaml`. Nothing is retyped.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from orchestrator.application.preflight.model import PreflightRequest
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import (
    ON_FAIL_KEY,
    REASON_NO_QUALITY_GATE,
    Plan,
    reason_no_field,
)
from orchestrator.application.use_cases.harness_readiness import (
    READINESS_BASE_BRANCH,
    READINESS_REPOSITORY_SLUG,
    READINESS_SPEC_FOLDER,
    READINESS_STORY_ID,
)
from orchestrator.application.use_cases.harness_readiness_seed import seed_readiness_project
from orchestrator.application.use_cases.preflight import _run_inputs
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import Project
from orchestrator.domain.entities.repository import Repository
from orchestrator.domain.values import PlannedRow
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)
WORK_DIR = Path("/work")
BMAD_VERSION = "6.11.0"

#: What `harness_readiness.start` names the branch, and the head the remote holds for it.
BRANCH = "readiness/claude/2026-03-04"
BRANCH_SHA = "b" * 40
BASE_SHA = "a" * 40

#: The fixture's one Story, read off disk so the plan expands what the image really ships.
STORIES_YAML = (
    fixtures.REPO_ROOT / "fixtures" / "readiness-repo" / READINESS_SPEC_FOLDER / "stories.yaml"
).read_text()

#: The rows `epic@1` plans for a one-Story readiness fixture, in file order.
READINESS_ROWS = [
    "plan",
    "checkout",
    "setup",
    "baseline",
    "stories[0].sync",
    "stories[0].build",
    "stories[0].verify",
    "stories[0].commit-guard",
    "e2e",
    "push",
    "link",
]

SETUP = "setup"
BASELINE = "baseline"
E2E = "e2e"
BUILD = "stories[0].build"
VERIFY = "stories[0].verify"


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
    """`epic@1` planned over the seeded Repository, through the product's own snapshot."""
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
        fixtures.tree("epic"),
        run_inputs,
        git=git,
        base_dir=WORK_DIR / "readiness" / READINESS_REPOSITORY_SLUG / "base",
        bmad_version=BMAD_VERSION,
    )


def row(result: Plan, path: str) -> PlannedRow:
    return next(entry for entry in result.rows if entry.path == path)


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


def test_the_readiness_plan_is_the_one_story_frame_in_file_order(readiness_plan: Plan) -> None:
    assert [entry.path for entry in readiness_plan.rows] == READINESS_ROWS


def test_baseline_is_skipped_at_plan_time_and_says_why(readiness_plan: Plan) -> None:
    """`baseline` runs the fast gate now, so the reason names that command and not the slow
    one. The fixture states none of the three, which is what makes every shell row skip."""
    baseline = row(readiness_plan, BASELINE)

    assert baseline.status == "skipped"
    assert baseline.reason == reason_no_field("unit_test_command")


def test_every_skipped_shell_row_names_the_command_it_asked_for(readiness_plan: Plan) -> None:
    """One reason per row, each naming its own field — the fixture declares no command at
    all, so this is where the three tiers are visible side by side (FR-8)."""
    reasons = {path: row(readiness_plan, path).reason for path in (SETUP, BASELINE, VERIFY, E2E)}

    assert reasons == {
        SETUP: reason_no_field("install_command"),
        BASELINE: reason_no_field("unit_test_command"),
        VERIFY: reason_no_field("unit_test_command"),
        E2E: REASON_NO_QUALITY_GATE,
    }


def test_baseline_still_declares_on_fail_fail(readiness_plan: Plan) -> None:
    """The row is skipped because there is nothing to run, not because `epic@1` was
    weakened: a red gate at baseline must still end a Run on a repository that was already
    broken."""
    assert row(readiness_plan, BASELINE).with_resolved[ON_FAIL_KEY] == "fail"


def test_the_readiness_run_reaches_its_agent_row(readiness_plan: Plan) -> None:
    """The whole point: nothing before the `build` row is skippable-or-failed, so the walk
    gets as far as dispatching the harness."""
    build = row(readiness_plan, BUILD)

    assert build.kind == "agent"
    assert build.status == "planned"
    assert build.story_id == READINESS_STORY_ID
    before_build = READINESS_ROWS[: READINESS_ROWS.index(BUILD)]
    assert [row(readiness_plan, path).status for path in before_build] == [
        "planned",  # plan
        "planned",  # checkout
        "skipped",  # setup — the fixture states no install_command
        "skipped",  # baseline — nor a unit_test_command
        "planned",  # stories[0].sync
    ]


def test_the_frames_verify_is_skipped_with_the_same_reason(readiness_plan: Plan) -> None:
    """The Story's own gate is the fast one, so it skips for the same reason `baseline` does."""
    verify = row(readiness_plan, VERIFY)

    assert verify.status == "skipped"
    assert verify.reason == reason_no_field("unit_test_command")


def test_no_row_of_the_readiness_plan_is_born_failed(readiness_plan: Plan) -> None:
    assert {entry.status for entry in readiness_plan.rows} == {"planned", "skipped"}
