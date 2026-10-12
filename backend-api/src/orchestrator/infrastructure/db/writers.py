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

from orchestrator.application.use_cases.announce import Announcer
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.notifier import Notifier
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTrajectoryRepository,
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
def open_writer_ports(
    session_factory: SessionFactory,
    git: Git | None = None,
    engine: WorkflowEngine | None = None,
    notifier: Notifier | None = None,
) -> Iterator[WriterPorts]:
    """One session's worth of `WriterPorts`, closed on every path.

    `git` is `None` for every caller that predates 5.9 (`attempt_writes`'s own scope has
    never needed it): `record_trajectory` degrades the same way `tracer`/`spend_writes` do.
    `trajectories` needs no adapter of its own beyond the session, so it is always built.
    `engine` is `None` for every caller that predates story 5-4: `_enqueue_dependents`
    degrades to a no-op when `None`, keeping every existing frozen `WriterPorts` unchanged.
    `notifier` is `None` for a scope that never changes a Run's status; otherwise it is the
    port every needs_you / terminal transition is announced through.
    """
    session = session_factory()
    try:
        runs = SQLAlchemyRunRepository(session)
        attempts = SQLAlchemyAttemptRepository(session)
        clock = SystemClock()
        announcer = (
            None
            if notifier is None
            else Announcer(
                notifier=notifier,
                projects=SQLAlchemyProjectRepository(session),
                repositories=SQLAlchemyRepositoryRepository(session),
                attempts=attempts,
                clock=clock,
            )
        )
        yield WriterPorts(
            runs=runs,
            steps=SQLAlchemyStepRunRepository(session),
            attempts=attempts,
            records=SQLAlchemyGateRecordRepository(session),
            uow=SessionUnitOfWork(session),
            clock=clock,
            announcer=announcer,
            git=git,
            trajectories=SQLAlchemyTrajectoryRepository(session),
            engine=engine,
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
