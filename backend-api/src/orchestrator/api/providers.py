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

from orchestrator.application.use_cases.projects import ProjectPorts
from orchestrator.domain.ports.git import Git
from orchestrator.infrastructure.clock import SystemClock
from orchestrator.infrastructure.db import (
    SQLAlchemyProjectRepository,
    SQLAlchemyRepositoryRepository,
    SQLAlchemyUnitOfWork,
)

#: The attributes `create_app` stores its adapters under.
SESSION_FACTORY = "session_factory"
CRYPTO = "crypto"
GIT = "git"


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
