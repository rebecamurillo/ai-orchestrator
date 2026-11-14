"""A Run's rows keep the role their pinned version declared (story 1, epic 2; AC3, AC4)."""

from __future__ import annotations

from orchestrator.domain.entities.template import TemplateVersion
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.application.test_create_run_use_case import Harness, base_request

NAME = "role-fixture"


def yaml_with(role: str) -> str:
    return f"""name: {NAME}
version: 1
steps:
  - id: build
    run: echo build
    role: {role}
  - id: other
    run: echo other
"""


def stored(version: int, role: str) -> TemplateVersion:
    return TemplateVersion(name=NAME, version=version, yaml=yaml_with(role), hash=f"h{version}")


def roles_of(harness: Harness, run_id) -> dict[str, str]:  # type: ignore[no-untyped-def]
    return {row.path: row.role for row in harness.steps.list_for_run(run_id)}


def test_the_stored_row_carries_the_declared_role_and_planner_rows_none() -> None:
    harness = Harness(git=fixtures.repo_init_git())
    harness.templates.add(stored(1, "implement"))

    result = harness.create(base_request(template_name=NAME))

    roles = roles_of(harness, result.run.id)
    assert roles["build"] == "implement"
    assert roles["other"] == ""
    assert {role for path, role in roles.items() if path not in ("build",)} == {""}


def test_a_later_version_does_not_change_the_runs_row() -> None:
    harness = Harness(git=fixtures.repo_init_git())
    harness.templates.add(stored(1, "implement"))
    result = harness.create(base_request(template_name=NAME))

    harness.templates.add(stored(2, "review"))

    assert roles_of(harness, result.run.id)["build"] == "implement"
