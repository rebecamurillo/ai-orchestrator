"""The SQLAlchemy adapter for the `UnitOfWork` port.

The semantics are the port's, and they are the ones `tests/unit/fakes/db.py` implements:
entering opens a session, leaving without an explicit `commit()` rolls back, and the
session is closed on every path. Use cases are written against the fake and executed
against this class, so any divergence would only ever surface in e2e — which is why the
two are asserted side by side in `tests/unit/test_db_adapters.py`.

Two failure modes are handled explicitly, because both lose information silently:

- **Entering twice.** The second `__enter__` would replace `self.session`, and the first
  session's connection would never return to the pool. It is refused.
- **A rollback that itself fails while an exception is already in flight.** Raising from
  `__exit__` replaces the exception the caller actually needs to see. The rollback failure
  is logged and the original error is allowed to propagate; with no exception in flight
  there is nothing to hide, and the rollback failure propagates as itself.
"""

from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:  # pragma: no cover — typing only
    from collections.abc import Callable

    from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


class SQLAlchemyUnitOfWork:
    """One transactional scope over one SQLAlchemy session."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None
        self.committed = False

    def __enter__(self) -> SQLAlchemyUnitOfWork:
        if self.session is not None:
            raise RuntimeError(
                "the unit of work is already open: entering twice would orphan its session"
            )
        self.session = self._session_factory()
        self.committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        session = self.session
        if session is None:  # pragma: no cover — `with` always pairs enter and exit
            return
        try:
            if not self.committed:
                self._rollback_without_hiding(session, exc)
        finally:
            # the connection returns to the pool whatever happened above
            session.close()
            self.session = None

    def _rollback_without_hiding(self, session: Session, exc: BaseException | None) -> None:
        """Discard the work, never replacing an exception the caller is already carrying."""
        try:
            session.rollback()
        except Exception:
            if exc is None:
                raise
            log.exception("rollback failed while another error was propagating")

    def commit(self) -> None:
        session = self._require_open("commit")
        session.commit()
        self.committed = True

    def rollback(self) -> None:
        session = self._require_open("rollback")
        session.rollback()

    def _require_open(self, action: str) -> Session:
        if self.session is None:
            raise RuntimeError(f"{action} outside the unit of work: it was not entered")
        return self.session
