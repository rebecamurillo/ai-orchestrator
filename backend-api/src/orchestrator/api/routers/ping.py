"""The smallest authenticated route there is.

It exists so that "the bearer dependency is attached and works" has something to be true
about before any feature router lands, and so `make e2e-api` and Schemathesis have one
operation under `/api/v1` to exercise against the running stack. It reads nothing and
writes nothing; the healthcheck is `/healthz`, which is public.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Pong(BaseModel):
    """The `/api/v1/ping` payload. Typed so the generated contract carries a schema (AD-3)."""

    pong: bool


@router.get("/ping", response_model=Pong, summary="Confirm the bearer token is accepted")
def ping() -> Pong:
    return Pong(pong=True)
