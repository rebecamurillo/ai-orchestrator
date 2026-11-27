"""One session's worth of `AdvancePorts` for the advance workflow (AD-37).

`create_run` shares the advance's unit of work, so the Run and `consumed_at` commit together.
`PreflightPorts` repeats `api/providers.py::_preflight_ports`, which `infrastructure` cannot
import (AD-2).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from sqlalchemy.orm import Session

from orchestrator.application.use_cases.create_run import CreateRunPorts
from orchestrator.application.use_cases.initiative_advance import AdvancePorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.domain.ports.remote_branches import RemoteBranches
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db.repositories import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyHarnessRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
)
from orchestrator.infrastructure.db.repositories.initiatives import (
    SQLAlchemyInitiativeAdvanceRepository,
    SQLAlchemyInitiativeRepository,
)
from orchestrator.infrastructure.db.repositories.run_records import SQLAlchemyRunRepositoryRecords
from orchestrator.infrastructure.db.writers import SessionFactory, SessionUnitOfWork
from orchestrator.infrastructure.harness.registry import build_harnesses
from orchestrator.infrastructure.process.logs import log_secrets
from orchestrator.infrastructure.process.runner import RealProcessRunner
from orchestrator.infrastructure.redact import redact
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.setup_record import FsSetupRecord
from orchestrator.infrastructure.skill_catalog import FsSkillCatalog
from orchestrator.infrastructure.tracing import build_tracer

ENGINE_NOT_BUILT = "the durable engine is not built: advance ports need it for create_run"


def create_run_ports(
    session: Session,
    uow: SessionUnitOfWork,
    settings: Settings,
    git: Git,
    engine: WorkflowEngine,
) -> CreateRunPorts:
    """`create_run`'s ports over `session`, so the Run commits with the caller's `uow`."""
    runs = SQLAlchemyRunRepository(session)
    preflight = PreflightPorts(
        git=git,
        templates=SQLAlchemyTemplateVersionRepository(session),
        runs=runs,
        harnesses=SQLAlchemyHarnessRepository(session),
        repositories=SQLAlchemyRepositoryRepository(session),
        projects=SQLAlchemyProjectRepository(session),
        skill_catalog=FsSkillCatalog(settings.agent_home),
        setup_record=FsSetupRecord(settings.agent_home),
        bmad_version=settings.bmad_version,
        max_active_runs=settings.max_active_runs,
        work_dir=settings.work_dir,
        harness_registry=build_harnesses(settings, RealProcessRunner()),
        verify_docker=settings.verify_docker,
    )
    return CreateRunPorts(
        preflight=preflight,
        engine=engine,
        steps=SQLAlchemyStepRunRepository(session),
        uow=uow,
        clock=SystemClock(),
        tracer=build_tracer(settings),
        run_repositories=SQLAlchemyRunRepositoryRecords(session),
        initiative_runs=runs,
    )


@contextmanager
def open_advance_ports(
    session_factory: SessionFactory,
    settings: Settings,
    git: Git,
    engine_ref: list[WorkflowEngine],
) -> Iterator[AdvancePorts]:
    """`AdvancePorts` over one session, closed on every path."""
    if not engine_ref:
        raise RuntimeError(ENGINE_NOT_BUILT)
    session = session_factory()
    try:
        uow = SessionUnitOfWork(session)
        runs = SQLAlchemyRunRepository(session)
        secrets = log_secrets(settings)

        def scrub(text: str) -> str:
            for secret in secrets:
                text = redact(text, secret)
            return text

        create = create_run_ports(session, uow, settings, git, engine_ref[0])
        yield AdvancePorts(
            initiatives=SQLAlchemyInitiativeRepository(session),
            advances=SQLAlchemyInitiativeAdvanceRepository(session),
            runs=runs,
            steps=create.steps,
            attempts=SQLAlchemyAttemptRepository(session),
            create_run=create,
            uow=uow,
            clock=create.clock,
            redact=scrub,
            branches=cast(RemoteBranches, git),
        )
    finally:
        session.close()
