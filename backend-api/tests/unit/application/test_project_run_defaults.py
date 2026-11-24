"""`set_run_defaults` (story 1 of epic 6): replace the five run defaults of a Project together."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from orchestrator.application.use_cases.project_run_defaults import RunDefaults, set_run_defaults
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.errors import Conflict, Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)

FULL = RunDefaults(
    default_budget_usd=Decimal("25.00"),
    default_harness="claude",
    default_model="claude-opus-5-5",
    default_autonomy="auto",
    default_senior_model="claude-opus-5-5",
)
EMPTY = RunDefaults(None, None, None, None, None)


def a_project(slug: str = "my-website", builtin: bool = False) -> Project:
    return Project(
        id=new_id(),
        slug=slug,
        name=slug,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        builtin=builtin,
        created_at=NOW,
        updated_at=NOW,
    )


def ports(project: Project) -> ProjectPorts:
    return ProjectPorts(
        uow=FakeUnitOfWork(),
        projects=FakeProjectRepository([project]),
        crypto=FakeCrypto(),
        clock=FakeClock(NOW),
    )


def test_the_five_defaults_are_stored_and_returned() -> None:
    project = a_project()
    p = ports(project)

    with p.uow:
        view = set_run_defaults(p, project.id, FULL)

    stored = p.projects.get(project.id)
    assert stored is not None
    for target in (view, stored):
        assert target.default_budget_usd == Decimal("25.00")
        assert target.default_harness == "claude"
        assert target.default_model == "claude-opus-5-5"
        assert target.default_autonomy == "auto"
        assert target.default_senior_model == "claude-opus-5-5"


def test_none_clears_every_default_and_the_write_commits_once() -> None:
    project = a_project()
    p = ports(project)
    with p.uow:
        set_run_defaults(p, project.id, FULL)
        before = p.uow.calls.count("commit")  # type: ignore[attr-defined]
        view = set_run_defaults(p, project.id, EMPTY)

    assert p.uow.calls.count("commit") - before == 1  # type: ignore[attr-defined]
    assert view.default_budget_usd is None
    assert view.default_harness is None
    assert view.default_autonomy is None


def test_an_unknown_project_is_not_found() -> None:
    p = ports(a_project())
    with p.uow, pytest.raises(NotFound):
        set_run_defaults(p, new_id(), FULL)


def test_the_readiness_project_is_refused() -> None:
    project = a_project(READINESS_PROJECT_SLUG, builtin=True)
    p = ports(project)
    with p.uow, pytest.raises(Conflict, match="built in"):
        set_run_defaults(p, project.id, FULL)


def _with(**changes: Any) -> RunDefaults:
    return RunDefaults(**{**FULL.__dict__, **changes})


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"default_budget_usd": Decimal("0")}, "default_budget_usd"),
        ({"default_budget_usd": Decimal("-1")}, "default_budget_usd"),
        ({"default_harness": "Claude"}, "default_harness"),
        ({"default_harness": ""}, "default_harness"),
        ({"default_harness": "claude\n"}, "default_harness"),
        ({"default_model": ""}, "default_model"),
        ({"default_model": "   "}, "default_model"),
        ({"default_senior_model": ""}, "default_senior_model"),
        ({"default_senior_model": " "}, "default_senior_model"),
        ({"default_autonomy": "manual"}, "default_autonomy"),
    ],
)
def test_a_default_that_breaks_its_rule_is_invalid_and_nothing_is_stored(
    changes: dict[str, Any], field: str
) -> None:
    project = a_project()
    p = ports(project)

    with p.uow, pytest.raises(Invalid, match=field):
        set_run_defaults(p, project.id, _with(**changes))

    stored = p.projects.get(project.id)
    assert stored is not None
    assert stored.default_harness is None
    assert "commit" not in p.uow.calls  # type: ignore[attr-defined]
