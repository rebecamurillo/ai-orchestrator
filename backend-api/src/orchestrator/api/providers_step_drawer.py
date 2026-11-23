"""The ports `GET /runs/{id}/steps/{seq}/attempts/{n}/drawer` reads through. Writes nothing."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.run_step_drawer import StepDrawerPorts
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.git.git_history import SubprocessGitHistory
from orchestrator.infrastructure.process.logs import RealLogReader, log_secrets


def step_drawer_ports(request: Request) -> Iterator[StepDrawerPorts]:
    session_factory = from_state(request, SESSION_FACTORY)
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield StepDrawerPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            logs=RealLogReader(log_secrets(settings)),
            history=SubprocessGitHistory(),
        )
