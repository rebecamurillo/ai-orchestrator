"""Ports for the Run worktree-file routes (6.2, 6.3, 6.6): the tree and file reads, the
Operator's spec edit, and the protected-path diff.

A module of its own, not three more functions on `api/providers.py` — that module crossed
its 400-line cap (`test_source_limits.py`), and the split-not-trim rule says a capped
module gains a sibling rather than a trimmed docstring; `providers_trajectories.py` is the
precedent. `api/providers.py` re-exports these three names: the frozen run-files router
tests and `routers/run_files.py` import them from there, and a re-export keeps the function
identity `app.dependency_overrides` keys on (`test_api_providers_run_files.py` pins it).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Query, Request

from orchestrator.api.providers_base import SESSION_FACTORY, from_state, required_git
from orchestrator.application.use_cases.run_files import (
    RunFilesDiffPorts,
    RunFilesPorts,
    RunFilesWritePorts,
)
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyAttemptRepository,
    SQLAlchemyGateRecordRepository,
    SQLAlchemyRunRepository,
    SQLAlchemyStepRunRepository,
    SQLAlchemyUnitOfWork,
)
from orchestrator.infrastructure.workspace.fs import FsWorkspace


def run_files_ports(request: Request) -> Iterator[RunFilesPorts]:
    """The ports `GET /runs/{id}/files` reads through (6.2). Writes nothing.

    `workspace` is `FsWorkspace` itself — a factory, not an instance — the same "port is
    the class" shape `infrastructure/dbos/startup.py` already wires `StepPorts.workspace`
    with: the use case cannot root one until it has read the Run's own `worktree_path`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesPorts(runs=SQLAlchemyRunRepository(uow.session), workspace=FsWorkspace)


def run_files_write_ports(request: Request) -> Iterator[RunFilesWritePorts]:
    """The ports `PUT /runs/{id}/files` writes through (6.3): `run_files_ports`'s own shape,
    plus `Git` to stage and commit the Operator's edit, a `GateRecordRepository` for the
    `spec_edit` line, a `Clock`, and the `UnitOfWork` itself so the use case can `commit()`.
    """
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesWritePorts(
            runs=SQLAlchemyRunRepository(uow.session),
            workspace=FsWorkspace,
            git=required_git(request, "run_files"),
            records=SQLAlchemyGateRecordRepository(uow.session),
            clock=SystemClock(),
            uow=uow,
        )


def run_files_diff_ports(
    request: Request, diff: Annotated[bool, Query()] = False
) -> Iterator[RunFilesDiffPorts | None]:
    """The ports `GET /runs/{id}/files?diff=1` reads through (6.6). Writes nothing.

    No `Workspace`: the diff is `Git`'s own answer over the worktree; the scope gate is the
    park's recorded hit list — see `application/use_cases/run_files.py`'s own docstring for
    why.

    Reads `?diff` itself and yields `None` when absent: FastAPI resolves every dependency on
    every request, so opening a session unconditionally would break the file and tree modes
    that share this route (same trap `run_views.py` documents for `board_view`).
    """
    if not diff:
        yield None
        return
    session_factory = from_state(request, SESSION_FACTORY)
    with SQLAlchemyUnitOfWork(session_factory) as uow:
        yield RunFilesDiffPorts(
            runs=SQLAlchemyRunRepository(uow.session),
            steps=SQLAlchemyStepRunRepository(uow.session),
            attempts=SQLAlchemyAttemptRepository(uow.session),
            records=SQLAlchemyGateRecordRepository(uow.session),
            git=required_git(request, "run_files"),
        )
