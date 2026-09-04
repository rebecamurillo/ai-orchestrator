"""Composition root: the only module that wires adapters into ports.

`DBOS.launch()` belongs here too, from Epic 4 on. Until then this process is a FastAPI
application: the public `/healthz`, and every feature router mounted under `/api/v1` behind
the one bearer dependency (AD-4).

`create_app` performs no I/O, and it is `main()` — never `create_app` — that wires
`alembic upgrade head` in as the application's start-up step. Why it is done that way, and
what it guarantees, is stated once in
`orchestrator.infrastructure.db.migrations`; this module is where it is wired.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from importlib.metadata import PackageNotFoundError, version

import uvicorn
from fastapi import Depends, FastAPI
from pydantic import BaseModel, ValidationError

from orchestrator.api.deps import require_bearer
from orchestrator.api.errors import UNAUTHORIZED_RESPONSE, install_error_handlers
from orchestrator.api.routers import ping
from orchestrator.infrastructure.db.migrations import run_migrations
from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings

API_PREFIX = "/api/v1"
HTTP_UNAUTHORIZED = 401

PACKAGE = "orchestrator"

#: What FastAPI accepts as `lifespan`: a callable taking the app and yielding once.
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def package_version() -> str:
    """The distribution version, or a marker when running from an uninstalled source tree."""
    try:
        return version(PACKAGE)
    except PackageNotFoundError:  # pragma: no cover — an installed package is the norm
        return "0.0.0+source"


class Health(BaseModel):
    """The `/healthz` payload. Typed so the generated contract carries a real schema (AD-3)."""

    status: str
    version: str


def migrating_lifespan(settings: Settings) -> Lifespan:
    """The start-up step that brings the schema to head before the socket is bound.

    Built here rather than inside `create_app` so that the only application that migrates
    is the one this module hands to uvicorn. See `infrastructure/db/migrations.py`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        run_migrations(settings)
        yield

    return lifespan


def create_app(settings: Settings, *, lifespan: Lifespan | None = None) -> FastAPI:
    """Build the ASGI application. Adapters are constructed here and nowhere else.

    Without a `lifespan` the application performs no I/O at any point in its life — the
    shape every unit test builds.
    """
    app = FastAPI(
        title="ai-orchestrator backend-api",
        version=package_version(),
        lifespan=lifespan,
    )
    # the settings object dependencies read; nothing else re-reads the environment (AD-20)
    app.state.settings = settings
    install_error_handlers(app)

    @app.get("/healthz", tags=["health"], response_model=Health)
    def healthz() -> Health:
        return Health(status="ok", version=package_version())

    # one dependency for the whole versioned surface: a feature router added later
    # inherits the bearer check — and its declared 401 — instead of having to remember them
    app.include_router(
        ping.router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_bearer)],
        responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE},
    )

    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        raise SystemExit(f"configuration error (AD-20): .env is incomplete\n{error}") from error

    configure_logging(settings.log_level)
    uvicorn.run(
        # the migration is the application's start-up step: uvicorn awaits it before it
        # binds, so the process never serves a half-migrated schema
        create_app(settings, lifespan=migrating_lifespan(settings)),
        # binds every interface: reached from the compose network, not from the host
        host="0.0.0.0",
        port=settings.backend_api_port,
        # uvicorn's default dictConfig would replace the JSON handler set just above,
        # leaving access and startup lines as plain text on the same stream
        log_config=None,
    )


if __name__ == "__main__":
    main()
