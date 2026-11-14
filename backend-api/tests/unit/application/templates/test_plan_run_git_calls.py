"""`plan_run` makes the calls it made before story 2, and reports the base tip it read (AC6)."""

from __future__ import annotations

from pathlib import Path

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.reader import PlanReader
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.templates.test_attach_mode import parsed
from tests.unit.fakes.git import FakeGit


def test_known_answers_from_the_memo_and_makes_no_call() -> None:
    git = FakeGit(refs={"main": "abc"})
    reader = PlanReader(git, base=Path("/base"), url="u")
    assert reader.known("main") is None
    assert git.calls == []
    assert reader.sha("main") == "abc"
    assert reader.known("main") == "abc"
    assert git.calls == [("ls_remote", ("u", "main"))]


def _plan(text: str, git: FakeGit, values: dict[str, str] | None = None):  # type: ignore[no-untyped-def]

    return plan_run(
        ResolvedTree(root=parsed(text), callees=()),
        fixtures.inputs(values=values or {"branch": BRANCH}),
        git=git,
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


TEMPLATE = """name: calls-fixture
version: 1
inputs:
  project:     { type: project,    required: true }
  repository:  { type: repository, required: true }
  base_branch: { type: string,     required: true }
  branch:      { type: string,     required: true }
steps:
  - id: checkout
    uses: git.worktree
    with: { base: "{{base_branch}}", branch: "{{branch}}" }
    gate: deterministic
"""
FROM_BASE = FROM_BRANCH = TEMPLATE
BRANCH = "feat/existing"


def test_a_plan_from_the_base_reads_the_base_once_and_reports_its_tip() -> None:

    git = fixtures.repo_init_git()
    plan = _plan(FROM_BASE, git)
    assert git.calls == EXPECTED_FROM_BASE
    assert plan.base_tip == fixtures.BASE_SHA


def test_a_plan_from_an_existing_branch_reports_no_base_tip() -> None:

    git = FakeGit(
        refs={fixtures.BASE_BRANCH: fixtures.BASE_SHA, "feat/existing": fixtures.WORK_SHA},
        files={},
        listings={},
    )
    plan = _plan(FROM_BRANCH, git)
    assert git.calls == EXPECTED_FROM_BRANCH
    assert plan.base_tip is None


URL = "https://github.com/org/my-repo.git"
EXPECTED_FROM_BASE = [
    ("ls_remote", (URL, "feat/existing")),
    ("ls_remote", (URL, "main")),
    ("ls_remote", (URL, "feat/existing-1")),
]
EXPECTED_FROM_BRANCH = [
    ("ls_remote", (URL, "feat/existing")),
    ("ls_remote", (URL, "feat/existing-1")),
]
