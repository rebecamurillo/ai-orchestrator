"""Every shipped root that takes a spec location hands each story row its own spec folder.

A property of the shipped set, selected by declared input name and never by template name
(story 7, 2026-11-06; gate H3, D8): whatever the shipped files are called or hold, a root
declaring `initiative_folder` or `spec_folder` plans, for each story, an `agent` row whose
resolved `spec_folder` is non-empty and, over an initiative, is the row's own epic's. It pins
no step id, order, count, graph shape or YAML text (hard rule 6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from orchestrator.application.dto import RunInputs
from orchestrator.application.templates.model import InputDecl, ParsedTemplate
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.use_cases.plan_run import resolve_tree
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.domain.entities.template import TemplateRef
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.git import FakeGit
from tests.unit.fakes.templates import FakeTemplateVersionRepository

SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"
SELECTING = ("initiative_folder", "spec_folder")
BRANCH = "feat/x"
FIXED_PATH = "docs/fixed"
EPIC_FOLDERS = ("epic-1", "epic-2")
SPEC_ONLY_FOLDER = "docs/spec"
INITIATIVE_EPICS = "".join(
    f"- id: e{n}\n  title: Epic {n}\n  branch: {BRANCH}\n  spec_folder: {folder}\n"
    f"  workdir: repos/r{n}\n"
    for n, folder in enumerate(EPIC_FOLDERS, start=1)
)


def stories_of(prefix: str) -> str:
    return "".join(
        f'- id: "{prefix}-{n}"\n  title: Story {n}\n  description: does thing {n}\n' for n in (1, 2)
    )


def seeded() -> FakeTemplateVersionRepository:
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(
        uow=uow, templates=templates, clock=FakeClock(datetime(2026, 11, 6, tzinfo=UTC))
    )
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


def fill(decl: InputDecl, selecting: str, folder: str) -> Any:
    """The fixture's value for one declared input; `None` leaves it unset."""
    if decl.name == selecting:
        return folder
    if decl.default is not None:
        return decl.default
    if not decl.required or decl.type in ("item", "project", "repository"):
        return None
    if decl.name == "base_branch":
        return fixtures.BASE_BRANCH
    if decl.name == "branch":
        return BRANCH
    return {"string": "m", "number": 1, "path": FIXED_PATH}.get(
        decl.type, decl.values[:1] and decl.values[0]
    )


def run_inputs(template: ParsedTemplate, selecting: str, folder: str) -> RunInputs:
    values = {
        decl.name: value
        for decl in template.inputs
        if (value := fill(decl, selecting, folder)) is not None
    }
    return fixtures.inputs(values=values)


def git_for(selecting: str) -> FakeGit:
    base = fixtures.BASE_SHA
    files: dict[tuple[str, str], str] = {}
    if selecting == "initiative_folder":
        files[(base, f"{fixtures.INITIATIVE_FOLDER}/epics.yaml")] = INITIATIVE_EPICS
        for n, folder in enumerate(EPIC_FOLDERS, start=1):
            files[(base, f"{fixtures.INITIATIVE_FOLDER}/{folder}/stories.yaml")] = stories_of(
                f"e{n}"
            )
    else:
        files[(base, f"{SPEC_ONLY_FOLDER}/stories.yaml")] = stories_of("s")
    return FakeGit(refs={fixtures.BASE_BRANCH: base}, files=files, listings={})


def selected() -> list[tuple[str, str]]:
    templates = seeded()
    chosen = []
    for name in sorted({summary.name for summary in templates.list()}):
        root = resolve_tree(
            templates, TemplateRef(name=name, version=max(templates.list_versions(name)))
        ).root
        declared = {decl.name for decl in root.inputs}
        for selecting in SELECTING:
            if selecting in declared:
                chosen.append((name, selecting))
                break
    return chosen


CHOSEN = selected()


def plan_of(name: str, selecting: str) -> Any:
    templates = seeded()
    tree = resolve_tree(
        templates, TemplateRef(name=name, version=max(templates.list_versions(name)))
    )
    folder = fixtures.INITIATIVE_FOLDER if selecting == "initiative_folder" else SPEC_ONLY_FOLDER
    return plan_run(
        tree,
        run_inputs(tree.root, selecting, folder),
        git=git_for(selecting),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )


def test_at_least_one_shipped_root_takes_a_spec_location() -> None:
    assert CHOSEN


@pytest.mark.parametrize(("name", "selecting"), CHOSEN)
def test_each_story_agent_row_resolves_a_non_empty_spec_folder(name: str, selecting: str) -> None:
    rows = [row for row in plan_of(name, selecting).rows if row.kind == "agent" and row.story_id]

    assert rows, name
    for row in rows:
        assert row.with_resolved.get("spec_folder"), (name, row.path)


@pytest.mark.parametrize(
    "name", [name for name, selecting in CHOSEN if selecting == "initiative_folder"]
)
def test_each_story_row_resolves_its_own_epics_spec_folder(name: str) -> None:
    rows = [
        row
        for row in plan_of(name, "initiative_folder").rows
        if row.kind == "agent" and row.story_id
    ]

    seen = set()
    for row in rows:
        epic = int(str(row.story_id).split("-")[0].removeprefix("e")) - 1
        assert str(row.with_resolved["spec_folder"]).endswith(EPIC_FOLDERS[epic]), (name, row.path)
        seen.add(row.with_resolved["spec_folder"])
    assert len(seen) == len(EPIC_FOLDERS)
