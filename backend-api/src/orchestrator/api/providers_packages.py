"""The ports the package routes read and write through, in a module of its own because
`api/providers.py` is at its line cap."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request

from orchestrator.api import providers_base
from orchestrator.api.providers_base import SESSION_FACTORY, SETTINGS, from_state
from orchestrator.application.use_cases.packages import PackagePorts
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectPackageRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
)


def package_ports(request: Request) -> Iterator[PackagePorts]:
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield PackagePorts(
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            packages=SQLAlchemyProjectPackageRepository(uow.session),
            templates=SQLAlchemyTemplateVersionRepository(uow.session),
            git=providers_base.required_git(request, "the package routes"),
            uow=uow,
            clock=SystemClock(),
            work_dir=from_state(request, SETTINGS).work_dir,
        )
