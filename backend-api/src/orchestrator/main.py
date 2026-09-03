"""Composition root: the only module that wires adapters into ports.

`DBOS.launch()` belongs here too, from Epic 4 on. Until then this process is a FastAPI
application with one unversioned route.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel, ValidationError

from orchestrator.infrastructure.logging import configure_logging
from orchestrator.infrastructure.settings import Settings

PACKAGE = "orchestrator"


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


def create_app(settings: Settings) -> FastAPI:
    """Build the ASGI application. Adapters are constructed here and nowhere else."""
    app = FastAPI(title="ai-orchestrator backend-api", version=package_version())

    @app.get("/healthz", tags=["health"], response_model=Health)
    def healthz() -> Health:
        return Health(status="ok", version=package_version())

    return app


def main() -> None:
    try:
        settings = Settings()
    except ValidationError as error:
        raise SystemExit(f"configuration error (AD-20): .env is incomplete\n{error}") from error

    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings),
        # binds every interface: reached from the compose network, not from the host
        host="0.0.0.0",
        port=settings.backend_api_port,
        # uvicorn's default dictConfig would replace the JSON handler set just above,
        # leaving access and startup lines as plain text on the same stream
        log_config=None,
    )


if __name__ == "__main__":
    main()
