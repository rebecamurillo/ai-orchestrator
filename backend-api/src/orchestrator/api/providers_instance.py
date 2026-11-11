"""The provider behind `GET /instance/activity` (AD-30).

A sibling of `providers.py`, which is at its line cap (`providers_base.py`: split, not trim).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.instance_activity import ActivityPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)


def activity_ports(request: Request) -> Iterator[ActivityPorts]:
    """The ports the activity read uses. Writes nothing, never commits."""
    settings = from_state(request, SETTINGS)
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as uow:
        yield ActivityPorts(
            queue=QueuePorts(
                engine=from_state(request, ENGINE),
                runs=SQLAlchemyRunRepository(uow.session),
                steps=SQLAlchemyStepRunRepository(uow.session),
                clock=SystemClock(),
                max_active_runs=settings.max_active_runs,
            ),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            dbos_application_version=str(settings.dbos_application_version),
        )
