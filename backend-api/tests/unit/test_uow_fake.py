"""The `UnitOfWork` port and the one fake every later story injects for it (AD-18).

The port exists so that a use case can say "these writes land together" without importing
`sqlalchemy`. The fake exists so `make test` never needs Postgres. Both land before the
adapter, and the adapter is then held to the semantics asserted here.
"""

from __future__ import annotations

import pytest

from orchestrator.domain.ports.unit_of_work import UnitOfWork
from tests.unit.fakes.db import FakeUnitOfWork


def test_the_fake_satisfies_the_port() -> None:
    uow: UnitOfWork = FakeUnitOfWork()

    assert isinstance(uow, UnitOfWork)


def test_entering_returns_the_unit_of_work_itself() -> None:
    uow = FakeUnitOfWork()

    with uow as entered:
        assert entered is uow


def test_a_clean_block_commits_only_when_asked() -> None:
    """A unit of work does not guess: nothing is committed without an explicit `commit()`."""
    uow = FakeUnitOfWork()

    with uow:
        pass

    assert uow.committed is False
    assert uow.rolled_back is True


def test_commit_inside_the_block_is_recorded() -> None:
    uow = FakeUnitOfWork()

    with uow:
        uow.commit()

    assert uow.committed is True
    assert uow.rolled_back is False


def test_an_exception_rolls_back_and_propagates() -> None:
    uow = FakeUnitOfWork()

    with pytest.raises(RuntimeError, match="boom"), uow:
        raise RuntimeError("boom")

    assert uow.rolled_back is True
    assert uow.committed is False


def test_an_exception_after_a_commit_leaves_the_commit_standing() -> None:
    uow = FakeUnitOfWork()

    with pytest.raises(RuntimeError, match="later"), uow:
        uow.commit()
        raise RuntimeError("later")

    assert uow.committed is True


def test_the_fake_records_what_it_was_asked_to_do_in_order() -> None:
    uow = FakeUnitOfWork()

    with uow:
        uow.commit()

    assert uow.calls == ["enter", "commit", "exit"]


def test_entering_twice_is_refused() -> None:
    """The adapter refuses it because a second session would leak a connection; the fake
    refuses it too, so a use case cannot be written against a behaviour only one of them has."""
    uow = FakeUnitOfWork()

    with uow, pytest.raises(RuntimeError, match="already open"):
        uow.__enter__()


def test_committing_outside_the_block_is_refused() -> None:
    """A commit with no open unit of work is a bug in the caller, not a no-op."""
    uow = FakeUnitOfWork()

    with pytest.raises(RuntimeError, match="not entered"):
        uow.commit()
