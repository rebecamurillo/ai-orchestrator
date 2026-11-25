"""`SQLAlchemyInitiativeRepository.add` maps a unique-index violation to the port's refusal."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from orchestrator.infrastructure.db.repositories.initiatives import SQLAlchemyInitiativeRepository
from tests.unit.initiative_fixtures import an_initiative


class RefusingSession:
    def __init__(self, error: Exception | None) -> None:
        self.error = error
        self.added: list[Any] = []

    def add(self, row: Any) -> None:
        self.added.append(row)

    def flush(self) -> None:
        if self.error is not None:
            raise self.error


def test_an_integrity_error_becomes_the_open_slug_refusal() -> None:
    cause = IntegrityError("insert", {}, Exception("uq_initiative_repository_slug_open"))
    repository = SQLAlchemyInitiativeRepository(RefusingSession(cause))  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="open initiative 'snake' already exists") as refusal:
        repository.add(an_initiative())

    assert refusal.value.__cause__ is cause


def test_a_clean_flush_adds_the_row() -> None:
    session = RefusingSession(None)

    SQLAlchemyInitiativeRepository(session).add(an_initiative())  # type: ignore[arg-type]

    assert len(session.added) == 1
