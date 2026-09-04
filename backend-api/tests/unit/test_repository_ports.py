"""The `RepositoryRepository` port and its fake (AD-18).

`domain/ports/repositories.py` is already paired by `tests/unit/test_project_ports.py`
(frozen, from 2.1); that file may not be edited to add the new Protocol or its fake
(AGENTS.md hard rule 1), so this module is the one place both are checked — structurally,
against the `Protocol`, and against the behaviour a use case is entitled to assume: a
repository that orders its list, scopes it to a Project, refuses a duplicate id, and answers
`None` for what it does not hold.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from orchestrator.domain.entities.repository import (
    DEFAULT_PACKAGE_MANAGER,
    DEFAULT_TEST_GLOBS,
    CloneCheck,
    Repository,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.repositories import RepositoryRepository
from tests.unit.fakes.projects import FakeRepositoryRepository

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)
LATER = datetime(2026, 9, 4, 13, 0, tzinfo=UTC)


def a_repository(project_id: UUID, **overrides: object) -> Repository:
    fields: dict[str, object] = {
        "id": new_id(),
        "project_id": project_id,
        "slug": "my-repo",
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
        "install_command": "",
        "quality_gate_command": "",
        "unit_test_command": "",
        "test_globs": DEFAULT_TEST_GLOBS,
        "package_manager": DEFAULT_PACKAGE_MANAGER,
        "clone_check": CloneCheck.pending(),
        "created_at": AT,
        "updated_at": AT,
    }
    fields.update(overrides)
    return Repository(**fields)  # type: ignore[arg-type]


def test_the_repository_fake_satisfies_the_port() -> None:
    repositories: RepositoryRepository = FakeRepositoryRepository()

    assert isinstance(repositories, RepositoryRepository)


def test_an_added_repository_is_found_by_id() -> None:
    repository = a_repository(new_id())
    repositories = FakeRepositoryRepository([repository])

    assert repositories.get(repository.id) == repository


def test_what_is_not_stored_is_none_rather_than_an_error() -> None:
    assert FakeRepositoryRepository().get(new_id()) is None


def test_list_by_project_is_ordered_by_creation_time_and_scoped_to_the_project() -> None:
    project_id = new_id()
    other_project = new_id()
    first = a_repository(project_id, created_at=AT, url="https://x/a.git")
    second = a_repository(project_id, created_at=LATER, url="https://x/b.git")
    elsewhere = a_repository(other_project, url="https://x/c.git")
    repositories = FakeRepositoryRepository([second, first, elsewhere])

    assert repositories.list_by_project(project_id) == [first, second]


def test_the_empty_list_is_a_list() -> None:
    assert FakeRepositoryRepository().list_by_project(new_id()) == []


def test_a_duplicate_id_is_refused_as_the_primary_key_would_refuse_it() -> None:
    repository = a_repository(new_id())
    repositories = FakeRepositoryRepository([repository])

    with pytest.raises(ValueError, match="already stored"):
        repositories.add(repository)


def test_update_replaces_the_stored_entity() -> None:
    repository = a_repository(new_id())
    repositories = FakeRepositoryRepository([repository])

    renamed = repository.model_copy(update={"default_branch": "develop"})
    repositories.update(renamed)

    assert repositories.get(repository.id) == renamed


def test_updating_something_that_was_never_added_is_refused() -> None:
    repositories = FakeRepositoryRepository()

    with pytest.raises(ValueError, match="no repository"):
        repositories.update(a_repository(new_id()))
