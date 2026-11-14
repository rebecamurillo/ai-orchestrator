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

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from types import TracebackType
from uuid import UUID

from sqlalchemy.orm import Session

from orchestrator.application.analysis.run_analysis import AnalysisScope
from orchestrator.application.use_cases.announce import Announcer
from orchestrator.application.use_cases.calculate_metrics import CalculationPorts
from orchestrator.application.use_cases.record_attempt_facts import FactsPorts
from orchestrator.application.use_cases.run_records import RecordPorts
from orchestrator.application.use_cases.spend import SpendPorts
from orchestrator.application.use_cases.writers import WriterPorts
from orchestrator.domain.entities.analysis import Analysis
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.log_facts import LogFacts
from orchestrator.domain.ports.notifier import Notifier
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyFactSetRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyGatewayReadRepository,
    SQLAlchemyInstanceHoldRepository,
    SQLAlchemyMetricCalculationRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyResultVersionRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTrajectoryRepository,
)
from orchestrator.infrastructure.db.repositories.analysis import SQLAlchemyAnalysisRepository
from orchestrator.infrastructure.db.repositories.run_records import (
    SQLAlchemyRunCommitRepository,
    SQLAlchemyRunRepositoryRecords,
)
from orchestrator.infrastructure.harness.facts import log_file_exists

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
            holds=SQLAlchemyInstanceHoldRepository(session),
            run_repositories=SQLAlchemyRunRepositoryRecords(session),
            calculations=SQLAlchemyMetricCalculationRepository(session),
            versions=SQLAlchemyResultVersionRepository(session),
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
            gateway_reads=SQLAlchemyGatewayReadRepository(session),
            clock=SystemClock(),
            uow=SessionUnitOfWork(session),
            fact_sets=SQLAlchemyFactSetRepository(session),
        )
    finally:
        session.close()


@contextmanager
def open_facts_ports(
    session_factory: SessionFactory,
    extractors: Mapping[str, LogFacts],
    log_exists: Callable[[str], bool] = log_file_exists,
    subscription_auth: bool | None = None,
) -> Iterator[FactsPorts]:
    """One session's worth of `FactsPorts`, closed on every path."""
    session = session_factory()
    try:
        yield FactsPorts(
            facts=SQLAlchemyFactSetRepository(session),
            uow=SessionUnitOfWork(session),
            clock=SystemClock(),
            extractors=extractors,
            log_exists=log_exists,
            subscription_auth=subscription_auth,
        )
    finally:
        session.close()


@contextmanager
def open_record_ports(session_factory: SessionFactory) -> Iterator[RecordPorts]:
    """One session's worth of `RecordPorts` for an executor's side record, closed on every path."""
    session = session_factory()
    try:
        yield RecordPorts(
            repositories=SQLAlchemyRunRepositoryRecords(session),
            commits=SQLAlchemyRunCommitRepository(session),
            uow=SessionUnitOfWork(session),
        )
    finally:
        session.close()


@contextmanager
def open_calculation_ports(
    session_factory: SessionFactory,
    gateway: Gateway,
    extractors: Mapping[str, LogFacts],
    log_exists: Callable[[str], bool] = log_file_exists,
    analysis: Callable[[UUID, UUID], Sequence[Analysis]] | None = None,
) -> Iterator[CalculationPorts]:
    """One session's worth of `CalculationPorts` for the metrics job, closed on every path."""
    session = session_factory()
    try:
        yield CalculationPorts(
            runs=SQLAlchemyRunRepository(session),
            steps=SQLAlchemyStepRunRepository(session),
            attempts=SQLAlchemyAttemptRepository(session),
            records=SQLAlchemyGateRecordRepository(session),
            holds=SQLAlchemyInstanceHoldRepository(session),
            calculations=SQLAlchemyMetricCalculationRepository(session),
            versions=SQLAlchemyResultVersionRepository(session),
            fact_sets=SQLAlchemyFactSetRepository(session),
            gateway_reads=SQLAlchemyGatewayReadRepository(session),
            run_records=SQLAlchemyRunRepositoryRecords(session),
            gateway=gateway,
            extractors=extractors,
            log_exists=log_exists,
            clock=SystemClock(),
            uow=SessionUnitOfWork(session),
            analyses=SQLAlchemyAnalysisRepository(session),
            analysis=analysis,
        )
    finally:
        session.close()


@contextmanager
def open_analysis_ports(session_factory: SessionFactory) -> Iterator[AnalysisScope]:
    """One session's worth of `AnalysisScope`: records to read, analyses to write."""
    session = session_factory()
    try:
        yield AnalysisScope(
            steps=SQLAlchemyStepRunRepository(session),
            attempts=SQLAlchemyAttemptRepository(session),
            run_records=SQLAlchemyRunRepositoryRecords(session),
            run_commits=SQLAlchemyRunCommitRepository(session),
            analyses=SQLAlchemyAnalysisRepository(session),
            uow=SessionUnitOfWork(session),
        )
    finally:
        session.close()
