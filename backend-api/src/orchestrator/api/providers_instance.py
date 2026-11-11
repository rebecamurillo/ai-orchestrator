"""The providers behind `/instance/*` (AD-30).

A sibling of `providers.py`, which is at its line cap (`providers_base.py`: split, not trim).
"""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.instance_activity import ActivityPorts
from orchestrator.application.use_cases.instance_hold import HoldPorts
from orchestrator.application.use_cases.queue import QueuePorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyInstanceHoldRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.db.writers import SessionUnitOfWork


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
                holds=SQLAlchemyInstanceHoldRepository(uow.session),
            ),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            dbos_application_version=str(settings.dbos_application_version),
        )


def hold_ports(request: Request) -> Iterator[HoldPorts]:
    """The ports the hold routes use. This one writes, through the use case's own commit;
    the outer scope only closes the session."""
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        yield HoldPorts(
            runs=SQLAlchemyRunRepository(scope.session),
            steps=SQLAlchemyStepRunRepository(scope.session),
            attempts=SQLAlchemyAttemptRepository(scope.session),
            holds=SQLAlchemyInstanceHoldRepository(scope.session),
            uow=SessionUnitOfWork(scope.session),
            clock=SystemClock(),
        )
