"""The initiative routers, mounted behind the one bearer outside `main.py`.

Epics 7 and 9 mount their routers here. `protected_routes` calls this once, and this module
reads `mount_protected` at call time so the two imports resolve.
"""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.api import protected_routes
from orchestrator.api.routers import initiatives, project_package


def install_initiative_routes(app: FastAPI) -> None:
    protected_routes.mount_protected(app, project_package.router)
    protected_routes.mount_protected(app, initiatives.router)
