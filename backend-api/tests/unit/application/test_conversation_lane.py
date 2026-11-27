"""A Run from an interactive template with a conversation row walks in the interactive lane
(epic 4 story 3, AC6). The templates are this test's own fixtures."""

from __future__ import annotations

from orchestrator.application.use_cases.create_run import CreateRunRequest
from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_partition import BUDGET, Harness

CONVERSING = """name: conversing
version: 1
type: interactive
steps:
{steps}"""

CONVERSATION = """  - id: {name}
    uses: conversation
    role: plan
    gate: human
    with: {{ step: {name}, skill: s, persona: p }}
    expect: {{ files: ["docs/{name}.md"], success: [done] }}
    prompts: {{ open: "o", close: "c {{attempt_id}}" }}
"""

MERGING = """  - id: merge
    uses: shell
    gate: deterministic
    with: { command: "true" }
"""


def run_of(steps: str) -> tuple[object, Harness]:
    harness = Harness()
    harness.templates.versions[("conversing", 1)] = TemplateVersion(
        name="conversing",
        version=1,
        yaml=CONVERSING.format(steps=steps),
        hash="sha",
        calls=(),
    )
    request = CreateRunRequest(
        template_name="conversing",
        template_version=1,
        project_id=fixtures.PROJECT.id,
        repository_id=fixtures.REPOSITORY.id,
        base_branch=fixtures.BASE_BRANCH,
        budget_usd=BUDGET,
    )
    return harness.create(request), harness


def test_four_conversation_steps_walk_in_the_interactive_lane() -> None:
    steps = "".join(CONVERSATION.format(name=name) for name in ("intake", "product", "ux", "tech"))

    result, harness = run_of(steps)

    run = result.run  # type: ignore[attr-defined]
    assert run.lane == "interactive"
    assert [args[2] for name, args in harness.engine.calls if name == "enqueue"] == ["interactive"]


def test_an_interactive_template_with_no_conversation_row_walks() -> None:
    result, harness = run_of(MERGING)

    run = result.run  # type: ignore[attr-defined]
    assert run.lane == "walk"
    assert [args[2] for name, args in harness.engine.calls if name == "enqueue"] == ["walk"]
