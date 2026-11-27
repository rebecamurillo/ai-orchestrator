"""The ports the Run list, the Board and the Run read routes read through.

Split out of `api/providers.py` at its line cap; `providers.py` imports the function back, so
`dependency_overrides[run_read_ports]` keys on the one object.
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import SESSION_FACTORY, from_state
from orchestrator.application.use_cases.run_read_ports import RunReadPorts
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyInitiativeRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.workspace.fs import FsWorkspace


def run_read_ports(request: Request) -> Iterator[RunReadPorts]:
    """The ports `GET /runs`, `GET /runs/{id}` and `GET /runs?view=board` (4.12) read
    through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunReadPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            gate_records=SQLAlchemyGateRecordRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            initiatives=SQLAlchemyInitiativeRepository(uow.session),
            templates=SQLAlchemyTemplateVersionRepository(uow.session),
            workspace=FsWorkspace,
        )
