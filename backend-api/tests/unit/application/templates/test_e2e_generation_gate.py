"""E2e generation gate: a gen-e2e agent step must precede the e2e shell step with bounded
redispatch.

story 4-6 (2026-09-17): e2e generation gate — gen-e2e skill step precedes e2e with bounded
redispatch; the skill name 'bmad-qa-generate-e2e-tests' is an architectural anchor and must
be updated if the skill is renamed.
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

#: `tests/unit/application/templates/test_e2e_generation_gate.py` -> the repository root.
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


def test_epic_has_e2e_generation_gate_with_bounded_redispatch() -> None:
    """story 4-6 (2026-09-17): e2e generation gate — gen-e2e skill step precedes e2e with
    bounded redispatch; the skill name 'bmad-qa-generate-e2e-tests' is an architectural
    anchor and must be updated if the skill is renamed.
    """
    templates = seeded()

    latest_version = max(templates.list_versions("epic"))
    stored = templates.versions[("epic", latest_version)]
    result = validate(stored.yaml, templates=templates)
    assert result.template is not None, result.errors

    top_level_steps = [s for s in result.template.steps if isinstance(s, Step)]

    # (d) Assert there is at least one agent step with the gen-e2e skill.
    gen_e2e_steps = [
        s
        for s in top_level_steps
        if s.uses == AGENT_KIND and ("skill", "bmad-qa-generate-e2e-tests") in s.params
    ]
    assert gen_e2e_steps, (
        "expected an agent step with skill 'bmad-qa-generate-e2e-tests' in the epic "
        "template; "
        f"top-level steps: {[s.id for s in top_level_steps]!r}"
    )

    # (e) Capture gen_e2e_id.
    gen_e2e_id = gen_e2e_steps[0].id

    # (f) Assert there is a shell step with redispatch == gen_e2e_id.
    shell_redispatch_steps = [
        s for s in top_level_steps if s.uses == "shell" and s.redispatch == gen_e2e_id
    ]
    assert shell_redispatch_steps, (
        f"expected a shell step with redispatch='{gen_e2e_id}' in the epic template; "
        f"shell steps: {[s.id for s in top_level_steps if s.uses == 'shell']!r}"
    )

    # (f-post) Assert a git.commit step exists between gen-e2e and the shell-redispatch step.
    gen_e2e_idx = top_level_steps.index(gen_e2e_steps[0])
    e2e_step_idx = top_level_steps.index(shell_redispatch_steps[0])
    between_steps = top_level_steps[gen_e2e_idx + 1 : e2e_step_idx]
    assert any(s.uses == "git.commit" for s in between_steps), (
        f"expected a git.commit step between '{gen_e2e_id}' and "
        f"'{shell_redispatch_steps[0].id}'; "
        f"found between them: {[s.uses for s in between_steps]!r}"
    )

    # (g) Assert redispatch_max is not None and >= 1.
    e2e_step = shell_redispatch_steps[0]
    assert e2e_step.redispatch_max is not None and e2e_step.redispatch_max >= 1, (
        f"expected redispatch_max >= 1 on shell step '{e2e_step.id}'; "
        f"got: {e2e_step.redispatch_max!r}"
    )
