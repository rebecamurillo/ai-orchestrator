"""Wiring `application/use_cases/harness_readiness_evaluate.py::evaluate` to a session of
its own (SPEC CAP-8) — the `WalkerDeps.on_terminal` hook's real adapter.

A session of its own, opened and closed around the read and the write, for the same reason
`infrastructure/db/run_finished.py::run_finished_hook` opens one: this call happens from
inside the walker's own step, after that step's `WriterPorts` session has already closed.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from orchestrator.application.use_cases.harness_readiness_evaluate import (
    HarnessEvaluatePorts,
    evaluate,
)
from orchestrator.domain.ports.gateway import Gateway
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.tracer import Tracer
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyHarnessRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
)
from orchestrator.infrastructure.db.writers import SessionFactory, SessionUnitOfWork


def readiness_evaluate_hook(  # noqa: PLR0913, PLR0917 — one positional per adapter, `run_finished_hook`'s own precedent
    session_factory: SessionFactory,
    git: Git | None,
    tracer: Tracer | None,
    gateway: Gateway | None,
    work_dir: Path,
    run_id: UUID,
) -> None:
    """One session's worth of `HarnessEvaluatePorts`, closed on every path."""
    session = session_factory()
    try:
        evaluate(
            HarnessEvaluatePorts(
                runs=SQLAlchemyRunRepository(session),
                steps=SQLAlchemyStepRunRepository(session),
                attempts=SQLAlchemyAttemptRepository(session),
                harnesses=SQLAlchemyHarnessRepository(session),
                projects=SQLAlchemyProjectRepository(session),
                repositories=SQLAlchemyRepositoryRepository(session),
                uow=SessionUnitOfWork(session),
                clock=SystemClock(),
                work_dir=work_dir,
                git=git,
                tracer=tracer,
                gateway=gateway,
            ),
            run_id,
        )
    finally:
        session.close()
