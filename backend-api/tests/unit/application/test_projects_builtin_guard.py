"""`update_project` refuses the built-in `readiness` Project (SPEC CAP-8): `_refuse_builtin`.

A new module, not an addition to whatever already tests `update_project`'s other rules —
hard rule 1 forbids appending to an existing test file, and this is a new branch, not a
revision of one that already exists.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.use_cases.projects import ProjectDraft, ProjectPorts, update_project
from orchestrator.domain.entities.project import READINESS_PROJECT_SLUG, Project
from orchestrator.domain.errors import Conflict
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository

NOW = datetime(2026, 3, 4, tzinfo=UTC)


def a_project(*, slug: str, builtin: bool) -> Project:
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


def test_updating_the_builtin_readiness_project_is_a_409() -> None:
    project = a_project(slug=READINESS_PROJECT_SLUG, builtin=True)
    project_ports = ports(project)

    with project_ports.uow, pytest.raises(Conflict, match="built in"):
        update_project(project_ports, project.id, ProjectDraft(name="new name"))


def test_updating_an_ordinary_project_is_unaffected() -> None:
    project = a_project(slug="my-website", builtin=False)
    project_ports = ports(project)

    with project_ports.uow:
        updated = update_project(project_ports, project.id, ProjectDraft(name="new name"))

    assert updated.name == "new name"
