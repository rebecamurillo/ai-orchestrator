"""The error vocabulary use cases raise.

`domain/` may not import `fastapi` (AD-2), so a use case cannot name a status code. It
raises one of these instead and the api layer decides the number — which is why this module
asserts the hierarchy and the message, and never a status.
"""

from __future__ import annotations

import inspect

import pytest

from orchestrator.domain import errors as domain_errors
from orchestrator.domain.errors import Conflict, DomainError, Invalid, NotFound

CONCRETE = (NotFound, Conflict, Invalid)


@pytest.mark.parametrize("error", CONCRETE)
def test_every_error_is_a_domain_error(error: type[DomainError]) -> None:
    assert issubclass(error, DomainError)


def test_a_domain_error_is_an_exception() -> None:
    assert issubclass(DomainError, Exception)


@pytest.mark.parametrize("error", CONCRETE)
def test_the_message_survives_the_raise(error: type[DomainError]) -> None:
    with pytest.raises(error, match="run 7"):
        raise error("run 7")


@pytest.mark.parametrize("error", CONCRETE)
def test_catching_the_base_catches_every_kind(error: type[DomainError]) -> None:
    with pytest.raises(DomainError):
        raise error("boom")


def test_the_kinds_are_distinct() -> None:
    """`except NotFound` must not swallow a `Conflict`."""
    with pytest.raises(Conflict):
        try:
            raise Conflict("already running")
        except NotFound:  # pragma: no cover — the point is that this never matches
            pytest.fail("Conflict was caught as NotFound")


def test_no_status_code_leaks_into_the_domain() -> None:
    """Mapping to HTTP is the api layer's job; a number here would duplicate it."""
    source = inspect.getsource(domain_errors)

    for status in ("404", "409", "422", "401"):
        assert status not in source
    assert "fastapi" not in source
