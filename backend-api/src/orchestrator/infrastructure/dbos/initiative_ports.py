"""`InitiativePorts` for the start-up reopen pass (epic 9 story 3).

The infrastructure twin of `api/providers_initiatives.initiative_ports`, which this layer cannot
import (AD-2): one session holds the repositories and the `create_run` ports, and the signal
writers commit in a session of their own.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import cast

from orchestrator.application.use_cases.initiatives import InitiativePorts
from orchestrator.application.use_cases.signal_apply import SignalPorts
from orchestrator.application.use_cases.signals import SignalEffectPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.environment import read_run_environment
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyProjectPackageRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyTemplateVersionRepository,
)
from orchestrator.infrastructure.db.repositories.initiatives import (
    SQLAlchemyInitiativeAdvanceRepository,
    SQLAlchemyInitiativeRepository,
)
from orchestrator.infrastructure.db.writers import (
    SessionFactory,
    SessionUnitOfWork,
    open_writer_ports,
)
from orchestrator.infrastructure.dbos.advance_ports import create_run_ports
from orchestrator.infrastructure.notify import build_notifier
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.settings import Settings


@contextmanager
def open_initiative_ports(
    session_factory: SessionFactory,
    settings: Settings,
    git: Git,
    engine: WorkflowEngine,
) -> Iterator[InitiativePorts]:
    """`InitiativePorts` over one session, closed on every path."""
    session = session_factory()
    try:
        uow = SessionUnitOfWork(session)
        with open_writer_ports(
            session_factory, git=git, engine=engine, notifier=build_notifier(settings)
        ) as writers:
            yield InitiativePorts(
                initiatives=SQLAlchemyInitiativeRepository(session),
                advances=SQLAlchemyInitiativeAdvanceRepository(session),
                projects=SQLAlchemyProjectRepository(session),
                repositories=SQLAlchemyRepositoryRepository(session),
                packages=SQLAlchemyProjectPackageRepository(session),
                templates=SQLAlchemyTemplateVersionRepository(session),
                runs=SQLAlchemyRunRepository(session),
                git=git,
                branches=cast(RemoteBranches, git),
                create_run=create_run_ports(session, uow, settings, git, engine),
                signals=SignalEffectPorts(
                    signal=SignalPorts(writers=writers, engine=engine),
                    git=git,
                    process=RealProcessRunner(),
                    work_dir=str(settings.work_dir),
                    read_environment=partial(
                        read_run_environment, session_factory, settings.bmad_version
                    ),
                ),
                uow=uow,
                clock=SystemClock(),
                work_dir=settings.work_dir,
            )
    finally:
        session.close()
