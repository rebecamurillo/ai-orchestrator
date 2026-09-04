"""The two new ports, and the fakes every other unit test injects through them (AD-18).

A fake that drifted from its port would make every use-case test a test of the fake. Both
are checked against the `Protocol` structurally, and against the behaviour a use case is
entitled to assume: a repository that orders its list, refuses a duplicate, and answers
`None` for what it does not hold; a crypto that is reversible, non-deterministic, and
refuses a token it never issued.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.project import Project
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.crypto import Crypto
from orchestrator.domain.ports.repositories import ProjectRepository
from tests.unit.fakes.crypto import FakeCrypto
from tests.unit.fakes.projects import FakeProjectRepository

AT = datetime(2026, 9, 4, 12, 0, tzinfo=UTC)


def a_project(name: str, slug: str) -> Project:
    return Project(
        id=new_id(),
        slug=slug,
        name=name,
        context_text="",
        context_paths=(),
        env_vars_enc=(),
        log_prompt_content=False,
        created_at=AT,
        updated_at=AT,
    )


# ── Crypto ───────────────────────────────────────────────────────────────────


def test_the_crypto_fake_satisfies_the_port() -> None:
    crypto: Crypto = FakeCrypto()

    assert isinstance(crypto, Crypto)


def test_the_crypto_fake_round_trips() -> None:
    crypto = FakeCrypto()

    token = crypto.encrypt("abcdefgh")

    assert crypto.decrypt(token) == "abcdefgh"


def test_the_crypto_fake_is_not_the_identity() -> None:
    """An identity double would let "stored encrypted" pass for code that stored in clear."""
    crypto = FakeCrypto()

    assert crypto.encrypt("abcdefgh") != "abcdefgh"


def test_two_encryptions_of_one_value_differ_as_they_do_under_fernet() -> None:
    crypto = FakeCrypto()

    assert crypto.encrypt("same") != crypto.encrypt("same")


def test_the_crypto_fake_refuses_a_token_it_never_issued() -> None:
    crypto = FakeCrypto()

    with pytest.raises(ValueError, match="never issued"):
        crypto.decrypt("gAAAAA-not-from-here")


def test_the_crypto_fake_records_what_it_was_asked() -> None:
    crypto = FakeCrypto()

    token = crypto.encrypt("abcdefgh")
    crypto.decrypt(token)

    assert crypto.encrypted == ["abcdefgh"]
    assert crypto.decrypted == [token]


# ── ProjectRepository ────────────────────────────────────────────────────────


def test_the_repository_fake_satisfies_the_port() -> None:
    projects: ProjectRepository = FakeProjectRepository()

    assert isinstance(projects, ProjectRepository)


def test_an_added_project_is_found_by_id_and_by_slug() -> None:
    project = a_project("My Website", "my-website")
    projects = FakeProjectRepository([project])

    assert projects.get(project.id) == project
    assert projects.get_by_slug("my-website") == project


def test_what_is_not_stored_is_none_rather_than_an_error() -> None:
    """Turning a miss into a `NotFound` is a rule, and rules live in `application/`."""
    projects = FakeProjectRepository()

    assert projects.get(new_id()) is None
    assert projects.get_by_slug("nothing") is None


def test_the_list_is_ordered_by_name_as_the_query_will_be() -> None:
    projects = FakeProjectRepository(
        [a_project("Charlie", "charlie"), a_project("alpha", "alpha"), a_project("Bravo", "bravo")]
    )

    assert [project.name for project in projects.list()] == ["Bravo", "Charlie", "alpha"]


def test_the_empty_list_is_a_list() -> None:
    assert FakeProjectRepository().list() == []


def test_a_duplicate_id_is_refused_as_the_primary_key_would_refuse_it() -> None:
    project = a_project("My Website", "my-website")
    projects = FakeProjectRepository([project])

    with pytest.raises(ValueError, match="already stored"):
        projects.add(project)


def test_a_duplicate_slug_is_refused_as_the_unique_index_would_refuse_it() -> None:
    projects = FakeProjectRepository([a_project("My Website", "my-website")])

    with pytest.raises(ValueError, match="slug"):
        projects.add(a_project("Another", "my-website"))


def test_update_replaces_the_stored_entity() -> None:
    project = a_project("My Website", "my-website")
    projects = FakeProjectRepository([project])

    renamed = project.model_copy(update={"name": "Renamed"})
    projects.update(renamed)

    assert projects.get(project.id) == renamed
    assert projects.list() == [renamed]


def test_updating_something_that_was_never_added_is_refused() -> None:
    projects = FakeProjectRepository()

    with pytest.raises(ValueError, match="no project"):
        projects.update(a_project("My Website", "my-website"))
