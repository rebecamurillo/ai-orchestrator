"""The routes AD-1 puts behind the one bearer dependency, mounted outside `main.py`.

`main.py` keeps its size under the source-limits gate, so a story that adds a router adds it
to `install_*_routes` here, never to `main.py`. The bearer check and its declared 401 come
from `mount_protected` and nowhere else (AD-4).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, FastAPI

from orchestrator.api.deps import require_bearer
from orchestrator.api.errors import UNAUTHORIZED_RESPONSE
from orchestrator.api.routers import metrics_catalogue, run_label

API_PREFIX = "/api/v1"
HTTP_UNAUTHORIZED = 401


def mount_protected(app: FastAPI, router: APIRouter) -> None:
    """One feature router, on the versioned prefix, behind the one bearer dependency (AD-4)."""
    app.include_router(
        router,
        prefix=API_PREFIX,
        dependencies=[Depends(require_bearer)],
        responses={HTTP_UNAUTHORIZED: UNAUTHORIZED_RESPONSE},
    )


def install_metrics_routes(app: FastAPI) -> None:
    mount_protected(app, metrics_catalogue.router)
    mount_protected(app, run_label.router)
