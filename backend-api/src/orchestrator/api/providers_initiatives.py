"""The ports the initiative use cases run on, in a module of its own because
`api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from fastapi import Request

from orchestrator.api import providers_base
from orchestrator.api.providers import _preflight_ports, signal_effect_ports
from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyInitiativeAdvanceRepository,
    SQLAlchemyInitiativeRepository,
    SQLAlchemyProjectPackageRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.db.repositories.run_records import SQLAlchemyRunRepositoryRecords
from orchestrator.infrastructure.tracing import build_tracer
from orchestrator.infrastructure.workspace.fs import FsWorkspace

NEEDED_BY = "the initiative routes"


def initiative_ports(request: Request) -> Iterator[InitiativePorts]:
    """One unit of work holds every repository; `signals` commits in a session of its own."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    git = providers_base.required_git(request, NEEDED_BY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        runs = SQLAlchemyRunRepository(uow.session)
        clock = SystemClock()
        create = CreateRunPorts(
            preflight=_preflight_ports(request, uow, "initiatives"),
            engine=engine,
            steps=SQLAlchemyStepRunRepository(uow.session),
            uow=uow,
            clock=clock,
            tracer=build_tracer(settings),
            run_repositories=SQLAlchemyRunRepositoryRecords(uow.session),
            initiative_runs=runs,
        )
        with contextmanager(signal_effect_ports)(request) as signals:
            yield InitiativePorts(
                initiatives=SQLAlchemyInitiativeRepository(uow.session),
                advances=SQLAlchemyInitiativeAdvanceRepository(uow.session),
                projects=SQLAlchemyProjectRepository(uow.session),
                repositories=SQLAlchemyRepositoryRepository(uow.session),
                packages=SQLAlchemyProjectPackageRepository(uow.session),
                templates=SQLAlchemyTemplateVersionRepository(uow.session),
                runs=runs,
                git=git,
                branches=cast(RemoteBranches, git),
                create_run=create,
                signals=signals,
                uow=uow,
                clock=clock,
                work_dir=settings.work_dir,
            )


def initiative_read_ports(request: Request) -> Iterator[InitiativeReadPorts]:
    """What the initiative list and detail read through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    git = providers_base.required_git(request, NEEDED_BY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        runs = SQLAlchemyRunRepository(uow.session)
        yield InitiativeReadPorts(
            initiatives=SQLAlchemyInitiativeRepository(uow.session),
            advances=SQLAlchemyInitiativeAdvanceRepository(uow.session),
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            runs=runs,
            initiative_runs=runs,
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            git=git,
            workspace=FsWorkspace,
            clock=SystemClock(),
        )
