"""A Template name PostgreSQL cannot hold is "no such template", not a 500.

`template_name` arrives in a request body (`POST /runs`, `POST /runs/preflight`), and
PostgreSQL `text` cannot contain a NUL byte: psycopg refuses the *parameter*, so a name
carrying one never reaches the server and comes back as a `DataError` — a 500 for what is
really an ordinary miss. The same column would refuse the insert, so no stored row can hold
a NUL either, and "matches nothing" is the honest answer.

The schemathesis gate found this through `POST /runs` (`template_name` = `"Ë\\x00;C"`), and
found it only on a run whose fuzzing happened to sample a NUL, so it is asserted here as
well: a unit test fires every time, a random one does not.

Driven over the same recording session double `test_template_repository_adapter.py` uses —
the point is that the adapter answers *without issuing a statement at all*.
"""

from __future__ import annotations

from typing import Any

import pytest

from orchestrator.infrastructure.db import SQLAlchemyTemplateVersionRepository
from orchestrator.infrastructure.db.repositories.templates import NUL

#: What the fuzzer sent, with the byte written where a reader can see it.
FUZZED = f"Ë{NUL};C"


class RefusingSession:
    """A session that fails the test if the adapter tries to execute anything."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def scalars(self, statement: Any) -> Any:
        self.statements.append(statement)
        raise AssertionError("a name with a NUL byte must not reach a query")


@pytest.fixture
def repository() -> tuple[SQLAlchemyTemplateVersionRepository, RefusingSession]:
    session = RefusingSession()
    return SQLAlchemyTemplateVersionRepository(session), session  # type: ignore[arg-type]


def test_the_nul_constant_is_the_byte_postgresql_refuses() -> None:
    assert NUL == "\x00"


def test_get_answers_none_without_querying(
    repository: tuple[SQLAlchemyTemplateVersionRepository, RefusingSession],
) -> None:
    store, session = repository

    assert store.get(FUZZED, 1) is None
    assert session.statements == []


def test_list_versions_answers_empty_without_querying(
    repository: tuple[SQLAlchemyTemplateVersionRepository, RefusingSession],
) -> None:
    store, session = repository

    assert store.list_versions(FUZZED) == []
    assert session.statements == []


def test_pinned_by_answers_zero_without_querying(
    repository: tuple[SQLAlchemyTemplateVersionRepository, RefusingSession],
) -> None:
    """`pinned_by` binds the name into a `jsonb` containment value, which refuses it too."""
    store, session = repository

    assert store.pinned_by(FUZZED, 1) == 0
    assert session.statements == []


def test_a_name_without_the_byte_is_still_looked_up(
    repository: tuple[SQLAlchemyTemplateVersionRepository, RefusingSession],
) -> None:
    """The guard is about one byte; every other name still reaches the database."""
    store, _session = repository

    with pytest.raises(AssertionError, match="must not reach a query"):
        store.get("epic", 1)
