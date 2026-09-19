"""Tests verifying story-run@1 seeds clean and plans one story frame.

story 4-8 (2026-09-17): story-run@1 template — ships for_each with only: bound to story_id;
template name and only: key are architectural anchors
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: Identical to `test_e2e_generation_gate.py`.
SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"

AT = datetime(2026, 9, 17, tzinfo=UTC)


def seeded() -> FakeTemplateVersionRepository:
    """Every shipped file, through the exact seeding `main.py` runs at start-up."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


def test_story_run_validates_clean() -> None:
    """story 4-8 (2026-09-17): story-run@1 template validates without errors."""
    templates = seeded()

    # Hard TDD gate: raises ValueError before the template exists
    latest_version = max(templates.list_versions("story-run"))

    stored = templates.versions[("story-run", latest_version)]
    result = validate(stored.yaml, templates=templates)
    assert result.template is not None, result.errors
    assert list(result.errors) == []


def test_story_run_plans_one_story_frame() -> None:
    """story 4-8 (2026-09-17): story-run@1 with story_id='2' plans exactly story '2'."""
    templates = seeded()

    latest_version = max(templates.list_versions("story-run"))
    stored_root = templates.versions[("story-run", latest_version)]
    result_root = validate(stored_root.yaml, templates=templates)
    assert result_root.template is not None, result_root.errors

    story_version = max(templates.list_versions("story"))
    stored_story = templates.versions[("story", story_version)]
    result_story = validate(stored_story.yaml, templates=templates)
    assert result_story.template is not None, result_story.errors

    tree = ResolvedTree(root=result_root.template, callees=(result_story.template,))

    run_inputs = fixtures.inputs(
        values={
            "branch": fixtures.EPIC_BRANCH,
            "spec_folder": fixtures.SPEC_FOLDER,
            "story_id": "2",
        }
    )
    plan = plan_run(
        tree,
        run_inputs,
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    story_ids = {r.story_id for r in plan.rows if r.story_id is not None}
    assert story_ids == {"2"}
