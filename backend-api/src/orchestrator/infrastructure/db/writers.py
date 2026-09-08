"""One scope for the three status writers, and the unit of work they enter inside it.

The writers are written to open their own transaction — `with ports.uow: … commit()` — and
`SQLAlchemyUnitOfWork` refuses a second `__enter__`, because entering it twice would orphan
the first session (`unit_of_work.py`). Both are right, and together they say what this
module is: the caller owns the session, the writer owns the transaction inside it.

`SessionUnitOfWork` is that inner half. It satisfies the `UnitOfWork` port over a session it
did not open and will not close: entering is a no-op, leaving without a commit discards the
work, and `commit` commits. `open_writer_ports` is the outer half — the session, the four
repositories and the clock, as one `WriterPorts` — and it is what the walker's every step
and (from 4.9) the signals router run one call inside.

A scope is a *step*, not a Run: the walker opens one, calls one writer, and closes it, so a
row that takes forty minutes holds no connection while it runs.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from types import TracebackType

from sqlalchemy.orm import Session

from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
)

#: How a scope reaches a session: `create_session_factory`'s own return shape.
SessionFactory = Callable[[], Session]


class SessionUnitOfWork:
    """A `UnitOfWork` over a session someone else opened, and someone else will close."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self.committed = False

    def __enter__(self) -> SessionUnitOfWork:
        self.committed = False
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self.committed:
            self._session.rollback()

    def commit(self) -> None:
        self._session.commit()
        self.committed = True

    def rollback(self) -> None:
        self._session.rollback()


@contextmanager
def open_writer_ports(session_factory: SessionFactory) -> Iterator[WriterPorts]:
    """One session's worth of `WriterPorts`, closed on every path."""
    session = session_factory()
    try:
        yield WriterPorts(
            runs=SQLAlchemyRunRepository(session),
            steps=SQLAlchemyStepRunRepository(session),
            attempts=SQLAlchemyAttemptRepository(session),
            records=SQLAlchemyGateRecordRepository(session),
            uow=SessionUnitOfWork(session),
            clock=SystemClock(),
        )
    finally:
        session.close()


@contextmanager
def open_spend_ports(session_factory: SessionFactory, gateway: Gateway) -> Iterator[SpendPorts]:
    """One session's worth of `SpendPorts` (5.7) — its own scope, since `attempt_writes`'
    `WriterPorts` may reach only `.attempts` (AD-8) and the budget read needs `runs`/`steps`
    too. `gateway` is the one adapter built once at the composition root, not per session."""
    session = session_factory()
    try:
        yield SpendPorts(
            gateway=gateway,
            runs=SQLAlchemyRunRepository(session),
            steps=SQLAlchemyStepRunRepository(session),
            attempts=SQLAlchemyAttemptRepository(session),
            uow=SessionUnitOfWork(session),
        )
    finally:
        session.close()
