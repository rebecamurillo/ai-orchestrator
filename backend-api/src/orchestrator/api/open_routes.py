"""The routes AD-1 opens without the bearer.

Kept out of `main.py` because `tests/unit/test_bearer_auth.py` reads every `include_router`
call there as a guarded one.
"""

from __future__ import annotations

from fastapi import FastAPI

from orchestrator.api.routers import guide


def install_open_routes(app: FastAPI) -> None:
    app.include_router(guide.router)
