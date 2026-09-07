"""The scripted repositories the plan tests share.

`plan_run` is pure apart from three `Git` calls, so a plan test is a fixture repository:
the four shipped Template files, a `stories.yaml` / `epics.yaml` text, a story file or two,
and the branches the remote is said to hold. They live here rather than in each test module
because the same repository answers several questions — the row list, the labels, the
skipped rules — and a second copy of it is how two of those answers would drift apart.

The Templates are the shipped files read verbatim off disk and run through the one
validator (AD-15), so a fixture can never describe a Template the repository does not ship.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

from orchestrator.application.dto import (
    DEFAULT_HARNESS,
    ProjectSnapshot,
    RepositorySnapshot,
    RunInputs,
)
from orchestrator.application.templates.model import ParsedTemplate
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.domain.entities.template import TemplateRef, TemplateVersion
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: `tests/unit/application/templates/plan_fixtures.py` -> the repository root.
REPO_ROOT = Path(__file__).resolve().parents[5]
TEMPLATES_DIR = REPO_ROOT / "templates"

NAMES = ("repo-init", "story", "epic", "initiative")

TEXTS: dict[str, str] = {name: (TEMPLATES_DIR / f"{name}.yaml").read_text() for name in NAMES}

#: Which callees each shipped root pins, in the order the planner walks them (AD-15).
CALLEES: dict[str, tuple[str, ...]] = {
    "repo-init": (),
    "story": (),
    "epic": ("story",),
    "initiative": ("epic", "story"),
}

#: The base clone `Git.read_file` and `Git.list_files` are asked of (AD-14).
BASE = Path("/work/my-project/my-repo/base")

BASE_SHA = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
WORK_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"
BMAD_VERSION = "6.11.0"

BASE_BRANCH = "main"
EPIC_BRANCH = "feat/epic-1"
INITIATIVE_BRANCH = "feat/initiative"
INIT_BRANCH = "chore/bmad-init"

SPEC_FOLDER = "docs/epic-1"
INITIATIVE_FOLDER = "docs/initiative"

PROJECT = ProjectSnapshot(
    id=UUID("01960000-0000-7000-8000-000000000001"),
    name="My Project",
    slug="my-project",
)

REPOSITORY = RepositorySnapshot(
    id=UUID("01960000-0000-7000-8000-000000000002"),
    slug="my-repo",
    url="https://github.com/org/my-repo.git",
    default_branch=BASE_BRANCH,
    install_command="uv sync",
    quality_gate_command="make check",
    unit_test_command="pytest -q",
    test_globs=("tests/**",),
)

#: The same repository with nothing to run for a quality gate — the `skipped` rule's input.
NO_QUALITY_GATE = REPOSITORY.model_copy(update={"quality_gate_command": None})


# --- the list files ------------------------------------------------------------------------

#: What the first story tells its dispatch to read, and how many retries `story@1` allows.
INVOKE_DEV_WITH = "Read the brief before planning."
RETRY_MAX = 2

EPIC_STORIES = f"""
- id: "1"
  title: The first story
  description: does the first thing
  invoke_dev_with: {INVOKE_DEV_WITH}
- id: "2"
  title: The second story
  description: does the second thing
  done_checkpoint: true
- id: "3"
  title: The third story
  description: does the third thing
"""

INITIATIVE_EPICS = f"""
- id: e1
  title: The first epic
  branch: {INITIATIVE_BRANCH}
  spec_folder: epic-1
  done_checkpoint: true
- id: e2
  title: The second epic
  branch: {INITIATIVE_BRANCH}
  spec_folder: epic-2
"""


def four_stories(prefix: str) -> str:
    """A `stories.yaml` of four entries whose ids carry the epic's number."""
    return "".join(
        f'- id: "{prefix}-{number}"\n  title: Story {number}\n  description: does thing {number}\n'
        for number in range(1, 5)
    )


def story_file(status: str) -> str:
    """One story file, as `bmad-build-auto` leaves it: frontmatter, then prose."""
    return f"---\ntitle: A story\nstatus: {status}\n---\n\n# A story\n"


DONE_STORY_PATH = f"{SPEC_FOLDER}/stories/3-the-third-story.md"
OPEN_STORY_PATH = f"{SPEC_FOLDER}/stories/1-the-first-story.md"
STORIES_DIR = f"{SPEC_FOLDER}/stories"


# --- the trees -----------------------------------------------------------------------------


def repository_of_versions() -> FakeTemplateVersionRepository:
    """All four shipped versions, `calls` pinned as saving each one would record them."""
    return FakeTemplateVersionRepository(
        [
            TemplateVersion(
                name=name,
                version=1,
                yaml=TEXTS[name],
                hash="sha",
                calls=tuple(TemplateRef(name=callee, version=1) for callee in CALLEES[name]),
            )
            for name in NAMES
        ]
    )


def parsed(name: str) -> ParsedTemplate:
    """One shipped Template, through the one parser there is."""
    result = validate(TEXTS[name], templates=repository_of_versions())
    assert result.template is not None, result.errors
    return result.template


def tree(name: str) -> ResolvedTree:
    """The pinned tree of one shipped Template: its root and every callee it reaches."""
    return ResolvedTree(
        root=parsed(name), callees=tuple(parsed(callee) for callee in CALLEES[name])
    )


# --- the inputs ----------------------------------------------------------------------------


def inputs(
    *,
    values: dict[str, Any] | None = None,
    repository: RepositorySnapshot = REPOSITORY,
    re_review_done: bool = False,
    harness: str = DEFAULT_HARNESS,
    model: str | None = None,
) -> RunInputs:
    """A `RunInputs` over the fixture Project and Repository."""
    return RunInputs(
        project=PROJECT,
        repository=repository,
        base_branch=BASE_BRANCH,
        values=values or {},
        re_review_done=re_review_done,
        harness=harness,
        model=model,
    )


def epic_inputs(**overrides: Any) -> RunInputs:
    return inputs(values={"branch": EPIC_BRANCH, "spec_folder": SPEC_FOLDER}, **overrides)


def initiative_inputs(**overrides: Any) -> RunInputs:
    return inputs(values={"initiative_folder": INITIATIVE_FOLDER}, **overrides)


# --- the scripted repositories -------------------------------------------------------------


def repo_init_git() -> FakeGit:
    """A remote holding `main` and not the branch `repo-init@1` would create."""
    return FakeGit(refs={BASE_BRANCH: BASE_SHA}, files={}, listings={})


def epic_git(*, done_story: bool = True) -> FakeGit:
    """A remote holding the epic branch, three stories, and one finished story file."""
    files = {(WORK_SHA, f"{SPEC_FOLDER}/stories.yaml"): EPIC_STORIES}
    listings: dict[tuple[str, str], list[str]] = {}
    if done_story:
        files[(WORK_SHA, DONE_STORY_PATH)] = story_file("done")
        files[(WORK_SHA, OPEN_STORY_PATH)] = story_file("in-progress")
        listings[(WORK_SHA, STORIES_DIR)] = [OPEN_STORY_PATH, DONE_STORY_PATH]
    return FakeGit(
        refs={BASE_BRANCH: BASE_SHA, EPIC_BRANCH: WORK_SHA}, files=files, listings=listings
    )


def initiative_files(ref: str = BASE_SHA) -> dict[tuple[str, str], str]:
    """`epics.yaml` at the base, and one `stories.yaml` per epic beside it."""
    return {
        (BASE_SHA, f"{INITIATIVE_FOLDER}/epics.yaml"): INITIATIVE_EPICS,
        (ref, f"{INITIATIVE_FOLDER}/epic-1/stories.yaml"): four_stories("4"),
        (ref, f"{INITIATIVE_FOLDER}/epic-2/stories.yaml"): four_stories("5"),
    }


def initiative_git(*, stories_at: str = BASE_SHA) -> FakeGit:
    """Two epics on one branch, eight stories, every list file at `stories_at`."""
    return FakeGit(
        refs={BASE_BRANCH: BASE_SHA, INITIATIVE_BRANCH: WORK_SHA},
        files=initiative_files(stories_at),
        listings={},
    )
