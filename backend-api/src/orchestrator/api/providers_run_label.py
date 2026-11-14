"""The ports `PATCH /runs/{id}` writes through (story 3), in a module of its own because
`api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import SESSION_FACTORY, from_state
from orchestrator.application.use_cases.run_label import RunLabelPorts
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)


def run_label_ports(request: Request) -> Iterator[RunLabelPorts]:
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunLabelPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            uow=uow,
        )
