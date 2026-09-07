"""Wiring `application/use_cases/run_finished.py::on_finished` to a session of its own.

A session of its own, opened and closed around the read and the write, for the same reason
`environment.py::read_run_environment` opens one: this call happens from inside the walker's
own step (4.10), after that step's `WriterPorts` session has already closed, and it must not
hold a connection for any longer than the one clone check it runs.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from orchestrator.application.use_cases.run_finished import RunFinishedPorts, on_finished
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
)
from orchestrator.infrastructure.db.writers import SessionFactory, SessionUnitOfWork


def run_finished_hook(
    session_factory: SessionFactory,
    git: Git | None,
    work_dir: Path,
    bmad_version: str,
    run_id: UUID,
) -> None:
    """One session's worth of `RunFinishedPorts`, closed on every path."""
    session = session_factory()
    try:
        on_finished(
            RunFinishedPorts(
                runs=SQLAlchemyRunRepository(session),
                repositories=SQLAlchemyRepositoryRepository(session),
                projects=SQLAlchemyProjectRepository(session),
                git=git,
                uow=SessionUnitOfWork(session),
                clock=SystemClock(),
                work_dir=work_dir,
                bmad_version=bmad_version,
            ),
            run_id,
        )
    finally:
        session.close()
