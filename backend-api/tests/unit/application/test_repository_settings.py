"""`set_initiative_folder` (story 2 of epic 6): the one writer of a Repository's folder."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.application.use_cases import projects as project_use_cases
from orchestrator.application.use_cases.projects import ProjectPorts, RepositoryDraft
from orchestrator.application.use_cases.repository_settings import set_initiative_folder
from orchestrator.domain.entities.repository import SUGGESTED_TEST_GLOBS, CloneCheck, Repository
from orchestrator.domain.errors import Invalid, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository

NOW = datetime(2026, 11, 22, tzinfo=UTC)
EARLIER = datetime(2026, 11, 1, tzinfo=UTC)


def a_repository() -> Repository:
    return Repository(
        id=new_id(),
        project_id=new_id(),
        slug="my-repo",
        url="https://github.com/org/my-repo.git",
        default_branch="main",
        install_command="",
        quality_gate_command="",
        unit_test_command="",
        test_globs=SUGGESTED_TEST_GLOBS,
        package_manager="other",
        clone_check=CloneCheck.pending(),
        created_at=EARLIER,
        updated_at=EARLIER,
    )


def ports(repository: Repository) -> ProjectPorts:
    return ProjectPorts(
        uow=FakeUnitOfWork(),
        projects=FakeProjectRepository([]),
        crypto=FakeCrypto(),
        clock=FakeClock(NOW),
        repositories=FakeRepositoryRepository([repository]),
    )


def commits(p: ProjectPorts) -> int:
    return p.uow.calls.count("commit")  # type: ignore[attr-defined]


def test_the_folder_is_stored_returned_and_committed_once() -> None:
    repository = a_repository()
    p = ports(repository)

    with p.uow:
        result = set_initiative_folder(p, repository.id, "specs/initiatives")

    stored = p.repositories.get(repository.id)  # type: ignore[union-attr]
    assert stored == result
    assert result.initiative_folder == "specs/initiatives"
    assert result.updated_at == NOW
    assert commits(p) == 1


def test_an_unknown_repository_is_not_found() -> None:
    p = ports(a_repository())

    with p.uow, pytest.raises(NotFound):
        set_initiative_folder(p, new_id(), "specs")
    assert commits(p) == 0


@pytest.mark.parametrize("folder", ["", "/abs", "a/../b", "a/./b", "a/", "a//b"])
def test_an_invalid_folder_names_the_rule_and_stores_nothing(folder: str) -> None:
    repository = a_repository()
    p = ports(repository)

    with p.uow, pytest.raises(Invalid, match=r"initiative_folder: must be one or more"):
        set_initiative_folder(p, repository.id, folder)

    assert p.repositories.get(repository.id) == repository  # type: ignore[union-attr]
    assert commits(p) == 0


def test_a_full_replace_update_keeps_the_folder() -> None:
    repository = a_repository()
    p = ports(repository)
    with p.uow:
        set_initiative_folder(p, repository.id, "specs/initiatives")
        updated = project_use_cases.update_repository(
            p, repository.id, RepositoryDraft(url=repository.url, default_branch="main")
        )

    assert updated.initiative_folder == "specs/initiatives"
