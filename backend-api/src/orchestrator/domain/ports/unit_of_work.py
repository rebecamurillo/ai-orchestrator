"""The `UnitOfWork` port.

A use case says "these writes land together" without naming a database: it takes a
`UnitOfWork`, works inside the context manager, and calls `commit()` when the whole
operation succeeded. Leaving the block without committing rolls back — a half-written Run
is never persisted because a later line raised.

The SQLAlchemy adapter lives in `infrastructure/db/unit_of_work.py`; the fake every unit
test injects is `tests/unit/fakes/db.py` (AD-18).
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol, runtime_checkable


@runtime_checkable
class UnitOfWork(Protocol):
    """One transactional scope, entered as a context manager."""

    def __enter__(self) -> UnitOfWork:
        """Open the scope and return it, so the caller can commit through it."""
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the scope, discarding anything not committed. Never swallows an exception."""
        ...

    def commit(self) -> None:
        """Make the work of this scope durable."""
        ...

    def rollback(self) -> None:
        """Discard the work of this scope."""
        ...
