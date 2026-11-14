"""The ports the run-metrics routes read and write through (epic 2 story 5), in a module of
its own because `api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, from_state
from orchestrator.api.routers.metrics_catalogue import catalogue_port
from orchestrator.application.metrics.live import MetricsReadPorts
from orchestrator.application.use_cases.analysis_sarif import AnalysisReadPorts
from orchestrator.application.use_cases.metric_calculations import CalculatePorts
from orchestrator.application.use_cases.metrics_compare import MetricsComparePorts
from orchestrator.application.use_cases.metrics_read import MetricsQueryPorts
from orchestrator.application.use_cases.metrics_spend import MetricsHomePorts
from orchestrator.application.use_cases.run_analyses import RunAnalysesPorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyFactSetRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyGatewayReadRepository,
    SQLAlchemyMetricCalculationRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyResultVersionRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.db.repositories.analysis import SQLAlchemyAnalysisRepository
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


def metrics_home_ports(request: Request) -> Iterator[MetricsHomePorts]:
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        session = scope.session
        yield MetricsHomePorts(
            projects=SQLAlchemyProjectRepository(session),
            runs=SQLAlchemyRunRepository(session),
            versions=SQLAlchemyResultVersionRepository(session),
            fact_sets=SQLAlchemyFactSetRepository(session),
            run_records=SQLAlchemyRunRepositoryRecords(session),
            clock=SystemClock(),
        )


def metrics_compare_ports(request: Request) -> Iterator[MetricsComparePorts]:
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        session = scope.session
        yield MetricsComparePorts(
            projects=SQLAlchemyProjectRepository(session),
            runs=SQLAlchemyRunRepository(session),
            steps=SQLAlchemyStepRunRepository(session),
            versions=SQLAlchemyResultVersionRepository(session),
            fact_sets=SQLAlchemyFactSetRepository(session),
            run_records=SQLAlchemyRunRepositoryRecords(session),
            catalogue=catalogue_port(),
            clock=SystemClock(),
            analyses=SQLAlchemyAnalysisRepository(session),
        )


def analysis_read_ports(request: Request) -> Iterator[AnalysisReadPorts]:
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        yield AnalysisReadPorts(
            analyses=SQLAlchemyAnalysisRepository(scope.session),
            uow=SessionUnitOfWork(scope.session),
        )


def run_analyses_ports(request: Request) -> Iterator[RunAnalysesPorts]:
    with SQLAlchemyUnitOfWork(from_state(request, SESSION_FACTORY)) as scope:
        session = scope.session
        yield RunAnalysesPorts(
            runs=SQLAlchemyRunRepository(session),
            versions=SQLAlchemyResultVersionRepository(session),
            analyses=SQLAlchemyAnalysisRepository(session),
            run_records=SQLAlchemyRunRepositoryRecords(session),
            templates=SQLAlchemyTemplateVersionRepository(session),
        )
