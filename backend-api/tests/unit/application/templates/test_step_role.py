"""A step's declared `role` (story 1, epic 2): a closed list the validator enforces."""

from __future__ import annotations

import pytest

from orchestrator.application.templates.plan import plan_run
from orchestrator.application.templates.plan_model import ResolvedTree
from orchestrator.application.templates.validate import validate
from tests.unit.application.templates import plan_fixtures as fixtures
from tests.unit.fakes.templates import FakeTemplateVersionRepository

ROLES = (
    "plan",
    "implement",
    "review",
    "verify",
    "spec-gate",
    "e2e-gen",
    "e2e",
    "retro",
    "orchestrate",
    "deterministic",
)


def text(role_line: str = "", second: str = "") -> str:
    return f"""name: fixture
version: 1
steps:
  - id: first
    run: echo one
{role_line}
  - id: second
    run: echo two
{second}
"""


def check(yaml_text: str):  # type: ignore[no-untyped-def]
    return validate(yaml_text, templates=FakeTemplateVersionRepository())


def test_an_unknown_role_is_reported_at_the_role_key_line() -> None:
    result = check(text("    role: build"))

    assert result.template is None
    assert [(e.line, e.reason) for e in result.errors] == [(6, "unknown role build")]


def test_a_non_string_role_is_reported_not_raised() -> None:
    result = check(text("    role: 3"))

    assert [e.reason for e in result.errors] == ["unknown role 3"]


@pytest.mark.parametrize("role", ROLES)
def test_every_listed_role_is_accepted_and_parsed(role: str) -> None:
    result = check(text(f"    role: {role}"))

    assert result.errors == ()
    assert result.template is not None
    first, second = result.template.steps
    assert first.role == role  # type: ignore[union-attr]
    assert second.role is None  # type: ignore[union-attr]


def test_role_on_a_for_each_construct_is_still_an_unknown_key() -> None:
    result = check(
        """name: fixture
version: 1
steps:
  - id: loop
    for_each: items
    as: item
    role: plan
    steps:
      - id: inner
        run: echo hi
"""
    )

    assert result.template is None
    assert any(e.reason == "unknown key" for e in result.errors)


def test_the_planner_writes_the_declared_role_and_empty_when_undeclared() -> None:
    result = check(text("    role: implement"))
    assert result.template is not None

    plan = plan_run(
        ResolvedTree(root=result.template, callees=()),
        fixtures.inputs(),
        git=fixtures.repo_init_git(),
        base_dir=fixtures.BASE,
        bmad_version=fixtures.BMAD_VERSION,
    )

    assert {row.path: row.role for row in plan.rows if row.path in ("first", "second")} == {
        "first": "implement",
        "second": "",
    }
