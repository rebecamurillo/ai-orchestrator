"""The ports the initiative use cases run on, in a module of its own because
`api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator
from typing import cast

from fastapi import Request

from orchestrator.api import providers_base
from orchestrator.api.providers import _preflight_ports
from orchestrator.api.providers_base import ENGINE, SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.signal_run import SignalPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
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
from orchestrator.infrastructure.db.writers import open_writer_ports
from orchestrator.infrastructure.harness.registry import build_harnesses
from orchestrator.infrastructure.notify import build_notifier
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.tracing import build_tracer

NEEDED_BY = "the initiative routes"


def initiative_ports(request: Request) -> Iterator[InitiativePorts]:
    """One unit of work holds every repository; `signals` commits in a session of its own."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    settings = from_state(request, SETTINGS)
    git = providers_base.required_git(request, NEEDED_BY)
    harnesses = build_harnesses(settings, RealProcessRunner())
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
        with SQLAlchemyUnitOfWork(session_factory) as preflight_uow:
            with open_writer_ports(
                session_factory, git=git, notifier=build_notifier(settings)
            ) as writers:
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
                    signals=SignalPorts(
                        writers=writers,
                        engine=engine,
                        harness_is_resumable=lambda name: (
                            name in harnesses and harnesses[name].capabilities.resume
                        ),
                        latest_attempt_for_run=writers.attempts.latest_for_run,
                        preflight=_preflight_ports(request, preflight_uow, "initiatives"),
                    ),
                    uow=uow,
                    clock=clock,
                    work_dir=settings.work_dir,
                )
