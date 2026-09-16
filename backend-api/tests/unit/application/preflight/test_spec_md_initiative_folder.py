"""SPEC.md (FR-8 line 7) for an initiative Run: `epics.yaml` declares each `spec_folder`
relative to the Initiative folder (PRD §3 "Initiative"), and `initiative@1` composes
`{{initiative_folder}}/{{epic.spec_folder}}` before anything reads it — so line 7 must
read `SPEC.md` under the composed path, not under the bare entry at the repository root.

Defect found 2026-09-16: pre-flight read `{spec_folder}/SPEC.md` verbatim and answered
`missing` for every epic of the v2-operability initiative while the files existed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.preflight import lists
from orchestrator.application.preflight.checks import Context
from orchestrator.application.preflight.model import CHECK_SPEC_MD, Line, PreflightRequest
from orchestrator.application.templates.plan_model import Plan
from orchestrator.domain.entities.repository import CloneCheck, Repository
from orchestrator.domain.ids import new_id
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.fakes.runs import FakeRunRepository

NOW = datetime(2026, 1, 1, tzinfo=UTC)

EPICS_TEXT = """
- id: e1
  title: The first epic
  branch: feat/e1
  spec_folder: epic-1
- id: e2
  title: The second epic
  branch: feat/e2
  spec_folder: epic-2
"""


def repo() -> Repository:
    return Repository(
        id=new_id(),
        project_id=new_id(),
        slug="my-repo",
        url="https://example.test/org/my-repo.git",
        default_branch="main",
        install_command="uv sync",
        quality_gate_command="make check",
        unit_test_command="pytest -q",
        test_globs=("tests/**",),
        package_manager="uv",
        clone_check=CloneCheck(status="ok", at=NOW, output="", bmad_version="6.11.0"),
        created_at=NOW,
        updated_at=NOW,
    )


def ctx(**overrides: object) -> Context:
    fields: dict[str, object] = {
        "git": FakeGit(),
        "base_dir": Path("/work/my-project/my-repo/base"),
        "bmad_version": "6.11.0",
        "max_active_runs": 2,
        "repository": repo(),
        "runs": FakeRunRepository(),
        "harnesses": FakeHarnessRepository(),
        "req": PreflightRequest(),
        "tree": None,
        "plan": None,
        "plan_error": None,
    }
    fields.update(overrides)
    return Context(**fields)  # type: ignore[arg-type]


def initiative_ctx(*, git: FakeGit, initiative_folder: str | None) -> Context:
    inputs = {"initiative_folder": initiative_folder} if initiative_folder is not None else {}
    return ctx(
        tree=fixtures.tree("initiative"),
        plan=Plan(plan_ref="sha", plan_refs={"docs/initiative/epics.yaml": "sha1"}, rows=()),
        git=git,
        req=PreflightRequest(inputs=inputs),
    )


def test_spec_folders_are_composed_under_the_initiative_folder() -> None:
    git = FakeGit(files={("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT})

    folders = lists.spec_folders(initiative_ctx(git=git, initiative_folder="docs/initiative"))

    assert folders == ("docs/initiative/epic-1", "docs/initiative/epic-2")


def test_spec_md_found_under_the_composed_path() -> None:
    git = FakeGit(
        files={
            ("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT,
            ("sha", "docs/initiative/epic-1/SPEC.md"): "# SPEC e1\n",
            ("sha", "docs/initiative/epic-2/SPEC.md"): "# SPEC e2\n",
        }
    )

    lines = lists.spec_md_lines(initiative_ctx(git=git, initiative_folder="docs/initiative"))

    assert lines == [
        Line(CHECK_SPEC_MD, "ok", "docs/initiative/epic-1: found"),
        Line(CHECK_SPEC_MD, "ok", "docs/initiative/epic-2: found"),
    ]


def test_spec_md_missing_names_the_composed_path() -> None:
    git = FakeGit(
        files={
            ("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT,
            ("sha", "docs/initiative/epic-1/SPEC.md"): "# SPEC e1\n",
        }
    )

    lines = lists.spec_md_lines(initiative_ctx(git=git, initiative_folder="docs/initiative"))

    assert lines == [
        Line(CHECK_SPEC_MD, "ok", "docs/initiative/epic-1: found"),
        Line(CHECK_SPEC_MD, "fail", "docs/initiative/epic-2: missing"),
    ]


def test_a_request_without_the_folder_input_keeps_the_bare_entries() -> None:
    """The incomplete-request path: no `initiative_folder` typed yet, nothing to compose."""
    git = FakeGit(files={("sha1", "docs/initiative/epics.yaml"): EPICS_TEXT})

    folders = lists.spec_folders(initiative_ctx(git=git, initiative_folder=None))

    assert folders == ("epic-1", "epic-2")
