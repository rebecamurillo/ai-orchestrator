"""story 4-9 (2026-09-17): task@1 template — pause_when: always →
spec_checkpoint True for all agent rows; template name is an architectural anchor"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.steps.agent import compose_prompt
from orchestrator.application.steps.agent_prompt import DISPATCH_INTENT, INTENT_KEY
from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: Identical to test_story_run_template.py.
SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"

AT = datetime(2026, 9, 17, tzinfo=UTC)


def seeded() -> FakeTemplateVersionRepository:
    """Every shipped file, through the exact seeding main.py runs at start-up."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


def test_task_validates_clean() -> None:
    """task@1 template validates without errors."""
    templates = seeded()

    # Hard TDD gate: raises ValueError before task.yaml exists
    latest_version = max(templates.list_versions("task"))

    stored = templates.versions[("task", latest_version)]
    result = validate(stored.yaml, templates=templates)
    assert result.template is not None, list(result.errors)
    assert list(result.errors) == []


def test_task_plan_has_unconditional_spec_checkpoint() -> None:
    """All agent rows in a task@1 plan have spec_checkpoint == True (pause_when: always)."""
    templates = seeded()

    latest_version = max(templates.list_versions("task"))
    stored = templates.versions[("task", latest_version)]
    result = validate(stored.yaml, templates=templates)
    assert result.template is not None, list(result.errors)

    tree = ResolvedTree(root=result.template, callees=())

    run_inputs = fixtures.inputs(
        values={
            "task_id": "gh-47",
            "title": "Fix auth",
            "intent": "gh-47: Fix the auth bug",
            "artifacts_dir": fixtures.SPEC_FOLDER,
            "branch": fixtures.EPIC_BRANCH,
        }
    )
    plan = plan_run(
        tree,
        run_inputs,
        git=fixtures.epic_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )
    agent_rows = [r for r in plan.rows if r.kind == "agent"]
    assert agent_rows, "No agent rows in task plan"
    assert all(r.with_resolved.get("spec_checkpoint") for r in agent_rows)
    # intent must flow through the planner into with_resolved so compose_prompt can use it
    assert all(r.with_resolved.get(INTENT_KEY) == "gh-47: Fix the auth bug" for r in agent_rows)
    first_prompt = compose_prompt(agent_rows[0].with_resolved, None, None)
    assert first_prompt.startswith(DISPATCH_INTENT.format(skill="bmad-build-auto"))
