"""Every rule the Repository use cases hold, over the fakes and never over a database (AD-18).

The rows of the story's I/O matrix that are use-case rules: the `test_globs` merge, the
duplicate-url conflict scoped to one Project, `clone_check` starting and staying `pending`
through a `PUT`, the slug derived from the url and numbered on collision within a Project,
and the unknown Project/Repository cases. Payload *shape* rows (a malformed glob, a missing
required field) are asserted in `tests/unit/test_repository_schemas.py`.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from orchestrator.application.use_cases.projects import (
    ProjectPorts,
    RepositoryDraft,
    add_repository,
    get_repository,
    list_repositories_by_project,
    update_repository,
)
from orchestrator.domain.entities.project import Project, slugify
from orchestrator.domain.entities.repository import DEFAULT_TEST_GLOBS
from orchestrator.domain.errors import Conflict, NotFound
from orchestrator.domain.ids import new_id
from tests.unit.fakes.clock import FakeClock
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.db import FakeUnitOfWork
from tests.unit.fakes.projects import FakeProjectRepository, FakeRepositoryRepository


class Ports:
    """The fakes, kept beside the `ProjectPorts` a use case receives."""

    def __init__(self) -> None:
        self.uow = FakeUnitOfWork()
        self.projects = FakeProjectRepository()
        self.repositories = FakeRepositoryRepository()
        self.crypto = FakeCrypto()
        self.clock = FakeClock()
        self.uow.__enter__()

    @property
    def ports(self) -> ProjectPorts:
        return ProjectPorts(
            uow=self.uow,
            projects=self.projects,
            repositories=self.repositories,
            crypto=self.crypto,
            clock=self.clock,
        )

    def project(self, name: str = "My Website") -> UUID:
        """Store a Project directly — the repository use cases need one to nest under."""
        project = Project(
            id=new_id(),
            slug=slugify(name),
            name=name,
            context_text="",
            context_paths=(),
            env_vars_enc=(),
            log_prompt_content=False,
            created_at=self.clock.now(),
            updated_at=self.clock.now(),
        )
        self.projects.add(project)
        return project.id


@pytest.fixture
def ports() -> Ports:
    return Ports()


def a_draft(**overrides: object) -> RepositoryDraft:
    fields: dict[str, object] = {
        "url": "https://github.com/org/my-repo.git",
        "default_branch": "main",
    }
    fields.update(overrides)
    return RepositoryDraft(**fields)  # type: ignore[arg-type]


# ── create ───────────────────────────────────────────────────────────────────


def test_a_minimal_create_stores_the_defaults(ports: Ports) -> None:
    project_id = ports.project()

    repository = add_repository(ports.ports, project_id, a_draft())

    assert repository.test_globs == DEFAULT_TEST_GLOBS
    assert repository.verify_skipped is True
    assert repository.clone_check.status == "pending"
    assert repository.clone_check.at is None
    assert repository.package_manager == "other"
    assert repository.project_id == project_id


def test_operator_globs_are_appended_after_the_defaults(ports: Ports) -> None:
    project_id = ports.project()

    repository = add_repository(ports.ports, project_id, a_draft(test_globs=("e2e/**",)))

    assert repository.test_globs == (*DEFAULT_TEST_GLOBS, "e2e/**")


def test_a_quality_gate_command_turns_off_verify_skipped(ports: Ports) -> None:
    project_id = ports.project()

    repository = add_repository(
        ports.ports, project_id, a_draft(quality_gate_command="make lint test")
    )

    assert repository.verify_skipped is False


def test_creating_commits(ports: Ports) -> None:
    project_id = ports.project()

    add_repository(ports.ports, project_id, a_draft())

    assert ports.uow.committed is True


def test_creating_records_both_timestamps_from_the_clock(ports: Ports) -> None:
    project_id = ports.project()

    repository = add_repository(ports.ports, project_id, a_draft())

    assert repository.created_at == ports.clock.now()
    assert repository.updated_at == ports.clock.now()


def test_creating_under_an_unknown_project_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no project with id"):
        add_repository(ports.ports, new_id(), a_draft())


def test_a_create_that_conflicts_never_commits(ports: Ports) -> None:
    project_id = ports.project()
    add_repository(ports.ports, project_id, a_draft())
    ports.uow.committed = False

    with pytest.raises(Conflict):
        add_repository(ports.ports, project_id, a_draft())

    assert ports.uow.committed is False


# ── the slug ─────────────────────────────────────────────────────────────────


def test_the_slug_is_derived_from_the_url(ports: Ports) -> None:
    project_id = ports.project()

    repository = add_repository(
        ports.ports, project_id, a_draft(url="https://github.com/org/My Repo.git")
    )

    assert repository.slug == "my-repo"


def test_a_colliding_slug_is_numbered_within_the_project(ports: Ports) -> None:
    project_id = ports.project()
    first = add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))
    second = add_repository(ports.ports, project_id, a_draft(url="https://y/org/repo.git"))

    assert (first.slug, second.slug) == ("repo", "repo-2")


def test_a_second_collision_keeps_numbering_upward(ports: Ports) -> None:
    """Two prior collisions, so the numbering walks past `-2` to find `-3`."""
    project_id = ports.project()
    first = add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))
    second = add_repository(ports.ports, project_id, a_draft(url="https://y/org/repo.git"))
    third = add_repository(ports.ports, project_id, a_draft(url="https://z/org/repo.git"))

    assert (first.slug, second.slug, third.slug) == ("repo", "repo-2", "repo-3")


def test_the_same_slug_is_reused_across_different_projects(ports: Ports) -> None:
    first_project = ports.project("First")
    second_project = ports.project("Second")

    first = add_repository(ports.ports, first_project, a_draft(url="https://x/org/repo.git"))
    second = add_repository(ports.ports, second_project, a_draft(url="https://y/org/repo.git"))

    assert (first.slug, second.slug) == ("repo", "repo")


# ── the duplicate-url conflict ────────────────────────────────────────────────


def test_a_second_repository_with_a_stored_url_in_the_same_project_is_a_conflict(
    ports: Ports,
) -> None:
    project_id = ports.project()
    add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))

    with pytest.raises(Conflict, match="already exists"):
        add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))


def test_the_same_url_under_a_different_project_is_accepted(ports: Ports) -> None:
    first_project = ports.project("First")
    second_project = ports.project("Second")
    add_repository(ports.ports, first_project, a_draft(url="https://x/org/repo.git"))

    repository = add_repository(ports.ports, second_project, a_draft(url="https://x/org/repo.git"))

    assert repository.project_id == second_project


# ── read ─────────────────────────────────────────────────────────────────────


def test_getting_returns_the_stored_repository(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft())

    assert get_repository(ports.ports, created.id) == created


def test_getting_an_unknown_id_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no repository with id"):
        get_repository(ports.ports, new_id())


def test_listing_an_unknown_project_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no project with id"):
        list_repositories_by_project(ports.ports, new_id())


def test_listing_comes_back_in_creation_order(ports: Ports) -> None:
    project_id = ports.project()
    first = add_repository(ports.ports, project_id, a_draft(url="https://x/org/one.git"))
    ports.clock.advance(60)
    second = add_repository(ports.ports, project_id, a_draft(url="https://x/org/two.git"))

    assert list_repositories_by_project(ports.ports, project_id) == [first, second]


def test_the_empty_list_is_a_list(ports: Ports) -> None:
    project_id = ports.project()

    assert list_repositories_by_project(ports.ports, project_id) == []


# ── update ───────────────────────────────────────────────────────────────────


def test_updating_changes_the_stated_fields(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft())
    ports.clock.advance(60)

    updated = update_repository(ports.ports, created.id, a_draft(default_branch="develop"))

    assert updated.default_branch == "develop"
    assert updated.updated_at > created.updated_at
    assert updated.created_at == created.created_at


def test_updating_never_touches_the_clone_check(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft())

    updated = update_repository(ports.ports, created.id, a_draft(default_branch="develop"))

    assert updated.clone_check == created.clone_check


def test_updating_never_changes_the_slug(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))

    updated = update_repository(ports.ports, created.id, a_draft(url="https://x/org/renamed.git"))

    assert updated.slug == created.slug
    assert updated.url == "https://x/org/renamed.git"


def test_updating_reapplies_the_test_globs_merge(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft(test_globs=("e2e/**",)))

    updated = update_repository(ports.ports, created.id, a_draft(test_globs=("spec/**",)))

    assert updated.test_globs == (*DEFAULT_TEST_GLOBS, "spec/**")


def test_updating_an_unknown_id_is_a_not_found(ports: Ports) -> None:
    with pytest.raises(NotFound, match="no repository with id"):
        update_repository(ports.ports, new_id(), a_draft())


def test_an_update_commits(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft())
    ports.uow.committed = False

    update_repository(ports.ports, created.id, a_draft(default_branch="develop"))

    assert ports.uow.committed is True


def test_renaming_the_url_onto_another_repositorys_url_in_the_same_project_is_a_conflict(
    ports: Ports,
) -> None:
    project_id = ports.project()
    add_repository(ports.ports, project_id, a_draft(url="https://x/org/taken.git"))
    mine = add_repository(ports.ports, project_id, a_draft(url="https://x/org/mine.git"))

    with pytest.raises(Conflict, match="already exists"):
        update_repository(ports.ports, mine.id, a_draft(url="https://x/org/taken.git"))


def test_keeping_a_repositorys_own_url_on_update_is_allowed(ports: Ports) -> None:
    project_id = ports.project()
    created = add_repository(ports.ports, project_id, a_draft(url="https://x/org/repo.git"))

    updated = update_repository(
        ports.ports,
        created.id,
        a_draft(url="https://x/org/repo.git", default_branch="develop"),
    )

    assert updated.default_branch == "develop"


def test_a_refused_update_leaves_the_stored_repository_alone(ports: Ports) -> None:
    project_id = ports.project()
    add_repository(ports.ports, project_id, a_draft(url="https://x/org/taken.git"))
    mine = add_repository(ports.ports, project_id, a_draft(url="https://x/org/mine.git"))
    ports.uow.committed = False

    with pytest.raises(Conflict):
        update_repository(ports.ports, mine.id, a_draft(url="https://x/org/taken.git"))

    assert get_repository(ports.ports, mine.id) == mine
    assert ports.uow.committed is False


# ── the repository port must be wired in ──────────────────────────────────────


def test_a_repository_use_case_without_the_port_fails_loudly(ports: Ports) -> None:
    """`ProjectPorts.repositories` defaults to `None` only for the frozen Project-only
    tests; a repository use case reached without it is a wiring bug, not a silent `None`."""
    incomplete = ProjectPorts(
        uow=ports.uow, projects=ports.projects, crypto=ports.crypto, clock=ports.clock
    )

    with pytest.raises(RuntimeError, match="repositories"):
        add_repository(incomplete, new_id(), a_draft())
