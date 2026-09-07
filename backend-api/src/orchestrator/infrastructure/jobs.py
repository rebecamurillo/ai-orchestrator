"""Wiring the two scheduled jobs (SPEC CAP-11) to the adapters `main()` already built.

`build_engine` gives the durable engine a walker; this module gives `main.run_migrations`'s
`schedule_jobs` step the two zero-argument callables `engine.schedule` (AD-6) registers —
each one opens its own `SQLAlchemyUnitOfWork` on every fire, the same way
`infrastructure/db/environment.py::read_run_environment` opens a session per read, rather
than holding one connection through however long a 3 AM cron window takes.

`crypto=None` below is the same shape `tests/unit/test_clone_check_use_cases.py::Harness`
builds `ProjectPorts` with: `clone_check` never reads the field, and building the real
`FernetCrypto` here would validate `ORCHESTRATOR_SECRET_KEY` on every process that ever
schedules this job — exactly the start-up-time failure `main.py::crypto_factory` defers to
the first Project write on purpose. `application/` is not typed against `None` there
(`ProjectPorts.crypto: Crypto`), so mypy would refuse it — but this module is
`infrastructure/`, which `make lint`'s `mypy` does not check (`pyproject.toml`'s own
`[tool.mypy] files` names only `domain` and `application`), the same reason the test's own
`# type: ignore[arg-type]` is a comment there and would be dead code here.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from pathlib import Path

from orchestrator.application.jobs.clone_check import run_clone_check_job
from orchestrator.application.jobs.worktree_gc import WorktreeGcPorts, run_worktree_gc
from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.db.environment import read_run_environment
from orchestrator.infrastructure.db.writers import SessionFactory
from orchestrator.infrastructure.settings import Settings
from orchestrator.infrastructure.workspace import FsWorkspace

#: The two names `engine.schedule` registers them under, and the crons read off `Settings`.
CLONE_CHECK_NAME = "clone_check"
WORKTREE_GC_NAME = "worktree_gc"

#: The directory every Run's log files live under (`application/steps/context.py::log_path`).
LOGS_DIRECTORY = "logs"


def _clone_check_job(
    session_factory: SessionFactory, git: Git, settings: Settings
) -> Callable[[], None]:
    def run() -> None:
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            ports = ProjectPorts(
                uow=uow,
                projects=SQLAlchemyProjectRepository(uow.session),
                crypto=None,  # module docstring: clone_check never encrypts anything
                clock=SystemClock(),
                repositories=SQLAlchemyRepositoryRepository(uow.session),
                git=git,
            )
            run_clone_check_job(
                ports, work_dir=settings.work_dir, bmad_version=settings.bmad_version
            )

    return run


def _worktree_gc_job(
    session_factory: SessionFactory, git: Git, settings: Settings
) -> Callable[[], None]:
    logs_root = str(Path(settings.work_dir) / LOGS_DIRECTORY)

    def run() -> None:
        with SQLAlchemyUnitOfWork(session_factory) as uow:
            ports = WorktreeGcPorts(
                uow=uow,
                runs=SQLAlchemyRunRepository(uow.session),
                git=git,
                logs=FsWorkspace(logs_root),
                clock=SystemClock(),
                read_environment=partial(
                    read_run_environment, session_factory, settings.bmad_version
                ),
                work_dir=str(settings.work_dir),
                retention_days=settings.worktree_retention_days,
            )
            run_worktree_gc(ports)

    return run


def scheduled_jobs(
    settings: Settings, session_factory: SessionFactory, git: Git
) -> list[tuple[str, str, Callable[[], None]]]:
    """`(name, cron, job)` for the two jobs SPEC CAP-11 registers, in that order."""
    return [
        (
            CLONE_CHECK_NAME,
            settings.clone_check_cron,
            _clone_check_job(session_factory, git, settings),
        ),
        (
            WORKTREE_GC_NAME,
            settings.worktree_gc_cron,
            _worktree_gc_job(session_factory, git, settings),
        ),
    ]
