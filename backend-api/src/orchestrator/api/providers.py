"""Where a request gets its ports.

`deps.py` holds the one credential check and nothing else — `tests/unit/test_bearer_auth.py`
ast-scans that module and fails on any comparison mentioning a token — so the wiring a
feature router needs lives here instead.

One dependency per feature, and each of them owns a transaction: `project_ports` opens a
`SQLAlchemyUnitOfWork`, builds the repository on *that* session, and hands the use case a
scope it only has to `commit()`. Leaving the dependency without a commit rolls back, so a
use case that raised — or a response model that refused the payload — persists nothing.

The adapters themselves are built by `main.py` and read off `app.state`: this module names
no `DATABASE_URL` and no key. `crypto` is a *factory* rather than an adapter, because
`ORCHESTRATOR_SECRET_KEY` is only validated when it is first used (see `main.py`), which
keeps a misconfigured instance startable and `/healthz` answerable.

It does not keep it usable. The factory is called here, on every request that needs these
ports, so an unusable key fails a `GET` exactly as it fails a `POST`. The refusal is a
`ValueError` naming the variable, and this module deliberately does not catch it: it
reaches `api/errors.py` as an unhandled exception, which logs the traceback — variable name
included — and answers a bare `internal server error` problem document. The body says
nothing, because a body that named the misconfigured secret would be the leak.

Nothing here asserts. `python -O` strips `assert`, and an application built without its
ports must answer a problem document, not silently dereference `None`.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request

from orchestrator.application.use_cases.create_run import CreateRunPorts, RunReadPorts
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.application.use_cases.preflight import PreflightPorts
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.application.use_cases.templates import TemplatePorts
from orchestrator.domain.ports.engine import WorkflowEngine
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyHarnessRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyTemplateVersionRepository,
    SQLAlchemyUnitOfWork,
)

#: The attributes `create_app` stores its adapters under.
SESSION_FACTORY = "session_factory"
CRYPTO = "crypto"
GIT = "git"
ENGINE = "engine"
SETTINGS = "settings"


def from_state(request: Request, attribute: str) -> Any:
    """One adapter off `app.state`, or a failure that says which one is missing."""
    value = getattr(request.app.state, attribute, None)
    if value is None:
        raise RuntimeError(
            f"app.state.{attribute} is not set: this application was built without it, "
            "and only main() wires the adapters"
        )
    return value


def git_adapter(request: Request) -> Git | None:
    """The git adapter, read tolerantly rather than through `from_state`.

    Every other adapter here is required, because no route can answer without it. This one
    is not: an application built without it still serves every Project and Repository
    operation, and only the clone check needs it — which then refuses loudly, naming the
    port, rather than this dependency refusing a read that never touches git.
    """
    adapter: Git | None = getattr(request.app.state, GIT, None)
    return adapter


def project_ports(request: Request) -> Iterator[ProjectPorts]:
    """The ports a Project use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    crypto = from_state(request, CRYPTO)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield ProjectPorts(
            uow=uow,
            projects=SQLAlchemyProjectRepository(uow.session),
            repositories=SQLAlchemyRepositoryRepository(uow.session),
            crypto=crypto(),
            clock=SystemClock(),
            git=git_adapter(request),
        )


def template_ports(request: Request) -> Iterator[TemplatePorts]:
    """The ports a Template use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield TemplatePorts(
            uow=uow,
            templates=SQLAlchemyTemplateVersionRepository(uow.session),
            clock=SystemClock(),
        )


def harness_ports(request: Request) -> Iterator[HarnessPorts]:
    """The ports a harness use case runs on, inside one transaction."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield HarnessPorts(uow=uow, harnesses=SQLAlchemyHarnessRepository(uow.session))


def _required_git(request: Request, needed_by: str) -> Git:
    """`git_adapter`, refusing loudly by name — pre-flight and `create_run` both need it."""
    git = git_adapter(request)
    if git is None:
        raise RuntimeError(
            f"app.state.git is not set: this application was built without it, "
            f"and {needed_by} needs a git port"
        )
    return git


def _preflight_ports(request: Request, uow: SQLAlchemyUnitOfWork, needed_by: str) -> PreflightPorts:
    """The `PreflightPorts` pre-flight and `create_run` (4.4) both run on, over one session
    — `create_run` reuses pre-flight's own resolution rather than building a second one."""
    settings = from_state(request, SETTINGS)
    return PreflightPorts(
        git=_required_git(request, needed_by),
        templates=SQLAlchemyTemplateVersionRepository(uow.session),
        runs=SQLAlchemyRunRepository(uow.session),
        harnesses=SQLAlchemyHarnessRepository(uow.session),
        repositories=SQLAlchemyRepositoryRepository(uow.session),
        projects=SQLAlchemyProjectRepository(uow.session),
        bmad_version=settings.bmad_version,
        max_active_runs=settings.max_active_runs,
        work_dir=settings.work_dir,
    )


def preflight_ports(request: Request) -> Iterator[PreflightPorts]:
    """The ports pre-flight runs on. Writes nothing, but still opens one transaction, the
    way `template_ports` does for its own read-only routes."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield _preflight_ports(request, uow, "pre-flight")


def create_run_ports(request: Request) -> Iterator[CreateRunPorts]:
    """The ports `create_run` (4.4) runs on: pre-flight's own, plus what only creation
    writes (`steps`, `engine`)."""
    session_factory = from_state(request, SESSION_FACTORY)
    engine: WorkflowEngine = from_state(request, ENGINE)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield CreateRunPorts(
            preflight=_preflight_ports(request, uow, "create_run"),
            engine=engine,
            steps=SQLAlchemyStepRunRepository(uow.session),
            uow=uow,
            clock=SystemClock(),
        )


def run_read_ports(request: Request) -> Iterator[RunReadPorts]:
    """The ports `GET /runs/{id}` reads through. Writes nothing."""
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunReadPorts(runs=SQLAlchemyRunRepository(uow.session))
