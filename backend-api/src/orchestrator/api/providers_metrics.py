"""The ports the run-metrics routes read and write through (epic 2 story 5), in a module of
its own because `api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, from_state
from orchestrator.application.metrics.live import MetricsReadPorts
from orchestrator.application.use_cases.metric_calculations import CalculatePorts
from orchestrator.application.use_cases.metrics_read import MetricsQueryPorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyFactSetRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyGatewayReadRepository,
    SQLAlchemyMetricCalculationRepository,
    SQLAlchemyResultVersionRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.db.repositories.run_records import SQLAlchemyRunRepositoryRecords
from orchestrator.infrastructure.db.writers import SessionUnitOfWork


def metrics_query_ports(request: Request) -> Iterator[MetricsQueryPorts]:
    """Reads only; the scope closes the session."""
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        session = scope.session
        yield MetricsQueryPorts(
            read=MetricsReadPorts(
                runs=SQLAlchemyRunRepository(session),
                steps=SQLAlchemyStepRunRepository(session),
                attempts=SQLAlchemyAttemptRepository(session),
                records=SQLAlchemyGateRecordRepository(session),
                fact_sets=SQLAlchemyFactSetRepository(session),
                gateway_reads=SQLAlchemyGatewayReadRepository(session),
                run_records=SQLAlchemyRunRepositoryRecords(session),
                clock=SystemClock(),
            ),
            versions=SQLAlchemyResultVersionRepository(session),
            calculations=SQLAlchemyMetricCalculationRepository(session),
        )


def calculate_ports(request: Request) -> Iterator[CalculatePorts]:
    """The manual calculation writes through the use case's own commit."""
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        yield CalculatePorts(
            runs=SQLAlchemyRunRepository(scope.session),
            calculations=SQLAlchemyMetricCalculationRepository(scope.session),
            versions=SQLAlchemyResultVersionRepository(scope.session),
            engine=from_state(request, ENGINE),
            clock=SystemClock(),
            uow=SessionUnitOfWork(scope.session),
        )
