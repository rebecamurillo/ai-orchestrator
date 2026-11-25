"""The ports the initiative use cases run on, in a module of its own because
`api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, cast

from fastapi import Query, Request

from orchestrator.api import providers_base
from orchestrator.api.providers import _preflight_ports, signal_effect_ports
from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.advance_retry import AdvanceRetryPorts
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.initiative_views import InitiativeReadPorts
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.open_initiative import OpenInitiativePorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SessionUnitOfWork,
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
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
from orchestrator.infrastructure.git.git_history import SubprocessGitHistory
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


def advance_retry_ports(request: Request) -> Iterator[AdvanceRetryPorts]:
    """What a run-defaults save wakes blocked advances through, on a session of its own.

    `retry_budget_advances` enters the unit of work itself, and `SQLAlchemyUnitOfWork` refuses
    a second entry, so the provider owns the session and hands over a `SessionUnitOfWork`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    session = session_factory()
    try:
        yield AdvanceRetryPorts(
            initiatives=SQLAlchemyInitiativeRepository(session),
            advances=SQLAlchemyInitiativeAdvanceRepository(session),
            uow=SessionUnitOfWork(session),
            engine=engine,
        )
    finally:
        session.close()


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
            records=SQLAlchemyGateRecordRepository(uow.session),
            history=SubprocessGitHistory(),
        )


def open_initiative_ports(
    request: Request, opened: Annotated[bool, Query()] = False
) -> Iterator[OpenInitiativePorts | None]:
    """What `?opened=true` writes through; `None` without it, so a plain read opens no session."""
    if not opened:
        yield None
        return
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield OpenInitiativePorts(
            initiatives=SQLAlchemyInitiativeRepository(uow.session),
            uow=uow,
            clock=SystemClock(),
        )
