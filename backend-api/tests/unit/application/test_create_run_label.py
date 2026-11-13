"""`create_run` stores a label on every Run (story 3; AC1, AC3)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.template import TemplateVersion
from orchestrator.domain.errors import Invalid
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_use_case import Harness, base_request

NAME = "bench-v1-staged"
AT = datetime(2026, 11, 10, 10, 23, 41, tzinfo=UTC)
YAML = f"""name: {NAME}
version: 3
steps:
  - id: build
    run: echo build
"""


def harness() -> Harness:
    made = Harness(git=fixtures.repo_init_git())
    made.templates.add(TemplateVersion(name=NAME, version=3, yaml=YAML, hash="h3"))
    made.clock.now = lambda: AT  # type: ignore[method-assign]
    return made


def test_the_default_label_is_stored_with_operator_false() -> None:
    made = harness()
    request = base_request(
        template_name=NAME,
        template_version=3,
        inputs={"initiative_folder": "initiatives/familio-snake-v2"},
    )

    result = made.create(request)

    stored = made.runs.runs[result.run.id]
    name = fixtures.PROJECT.name
    assert stored.label == f"{name} familio-snake-v2 {NAME} 2026-11-10 10:23"
    assert stored.label_set_by_operator is False


def test_a_given_label_is_trimmed_and_marked_the_operators() -> None:
    made = harness()

    result = made.create(
        base_request(template_name=NAME, template_version=3, label="  snake round 2  ")
    )

    stored = made.runs.runs[result.run.id]
    assert (stored.label, stored.label_set_by_operator) == ("snake round 2", True)


@pytest.mark.parametrize("label", ["   ", "x" * 121])
def test_a_label_out_of_bounds_is_invalid_and_nothing_is_stored(label: str) -> None:
    made = harness()

    with pytest.raises(Invalid):
        made.create(base_request(template_name=NAME, template_version=3, label=label))

    assert not any(name == "add" for name, _ in made.runs.calls)
    assert made.steps.steps == {}
