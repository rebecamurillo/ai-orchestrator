"""Retrospective step in the epic tail: a retro agent step (skill: bmad-retrospective) and a
commit-retro step must precede push.

story 4-7 (2026-09-17): retrospective step in the epic tail — a retro agent step (skill:
bmad-retrospective) and a commit-retro step precede push; the skill name 'bmad-retrospective'
is an architectural anchor and must be updated if the skill is renamed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from orchestrator.application.steps import AGENT_KIND
from orchestrator.application.templates.model import Step
from orchestrator.application.templates.validate import validate
from orchestrator.application.use_cases.templates import TemplatePorts, seed_shipped
from orchestrator.infrastructure.templates_loader import load_shipped_templates
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.templates import FakeTemplateVersionRepository

#: `tests/unit/application/templates/test_retro_step.py` -> the repository root.
SHIPPED_DIR = Path(__file__).resolve().parents[5] / "templates"

AT = datetime(2026, 9, 10, tzinfo=UTC)


def seeded() -> FakeTemplateVersionRepository:
    """Every shipped file, through the exact seeding `main.py` runs at start-up."""
    templates = FakeTemplateVersionRepository()
    uow = FakeUnitOfWork()
    uow.__enter__()
    ports = TemplatePorts(uow=uow, templates=templates, clock=FakeClock(AT))
    seed_shipped(ports, load_shipped_templates(SHIPPED_DIR))
    return templates


def test_epic_has_retro_step_committed_before_push() -> None:
    """story 4-7 (2026-09-17): retrospective step in the epic tail — a retro agent step
    (skill: bmad-retrospective) and a commit-retro step precede push; the skill name
    'bmad-retrospective' is an architectural anchor and must be updated if the skill is
    renamed.
    """
    templates = seeded()

    # (a) Load the latest shipped epic version.
    latest_version = max(templates.list_versions("epic"))
    stored = templates.versions[("epic", latest_version)]
    result = validate(stored.yaml, templates=templates)

    # (b) Validate the template.
    assert result.template is not None, result.errors

    # (c) Collect top-level steps.
    top_level_steps = [s for s in result.template.steps if isinstance(s, Step)]

    # (d) Assert there is at least one agent step with the bmad-retrospective skill.
    retro_steps = [
        s
        for s in top_level_steps
        if s.uses == AGENT_KIND and ("skill", "bmad-retrospective") in s.params
    ]
    assert retro_steps, (
        "expected an agent step with skill 'bmad-retrospective' in the epic template; "
        f"top-level steps: {[s.id for s in top_level_steps]!r}"
    )

    # (e) Capture retro_idx.
    retro_idx = top_level_steps.index(retro_steps[0])

    # (e2) Assert retro follows the e2e step.
    # The step id "e2e" is an anchor: update if the e2e step is renamed.
    e2e_steps = [s for s in top_level_steps if s.id == "e2e"]
    assert e2e_steps, (
        "expected a step with id 'e2e' in the epic template; "
        f"top-level steps: {[s.id for s in top_level_steps]!r}"
    )
    e2e_idx = top_level_steps.index(e2e_steps[0])
    assert e2e_idx < retro_idx, (
        f"expected e2e step (index {e2e_idx}) to precede retro step "
        f"(index {retro_idx}); "
        f"top-level steps: {[s.id for s in top_level_steps]!r}"
    )

    # (f) Find the push step and assert retro precedes it.
    push_steps = [s for s in top_level_steps if s.id == "push"]
    assert len(push_steps) == 1, (
        f"expected exactly one step with id 'push'; found: {[s.id for s in top_level_steps]!r}"
    )
    push_idx = top_level_steps.index(push_steps[0])
    assert retro_idx < push_idx, (
        f"expected retro step (index {retro_idx}) to precede push step "
        f"(index {push_idx}); "
        f"top-level steps: {[s.id for s in top_level_steps]!r}"
    )

    # (g) Assert there is a git.commit step between retro and push.
    between_steps = top_level_steps[retro_idx + 1 : push_idx]
    assert any(s.uses == "git.commit" for s in between_steps), (
        f"expected a git.commit step between retro (index {retro_idx}) and push "
        f"(index {push_idx}); "
        f"found between them: {[s.uses for s in between_steps]!r}"
    )
