"""The dependencies every versioned route carries (AD-4).

There is one credential in this system, `ORCHESTRATOR_TOKEN`, and one place that checks it.
The dependency is attached to the whole `/api/v1` router by the composition root rather than
to each route, so a feature router added in a later story inherits it and cannot forget it.

Four details are deliberate:

- **An empty configured token refuses everything.** `hmac.compare_digest(b"", b"")` is
  `True`, so an instance whose token is blank would accept a request with no
  `Authorization` header at all. The empty case is answered before any comparison: a
  misconfigured instance fails closed.
- **`HTTPBearer(auto_error=False)`.** Left on, the scheme answers a missing header with its
  own 403 in FastAPI's shape; off, every refusal is the same `Problem` and the same body.
- **Both sides are encoded before comparison.** `hmac.compare_digest` raises `TypeError` on
  a non-ASCII `str`, and a junk `Authorization` header must be a 401, never a 500.
- **The refusal carries no detail, and always the same challenge.** A body that
  distinguished "missing" from "wrong" would tell an attacker which half of the guess was
  right; `WWW-Authenticate` is required on a 401 (RFC 9110 §15.5.2) and is a header, so it
  varies nothing about the body.
"""

from __future__ import annotations

import hmac
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from orchestrator.api.errors import Problem
from orchestrator.infrastructure.settings import Settings

HTTP_UNAUTHORIZED = 401

#: The challenge a 401 must carry. `Bearer` alone: no realm, no scope, nothing to probe.
UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}

#: Declared so the generated contract (AD-3) and Schemathesis both know the scheme exists.
bearer_scheme = HTTPBearer(auto_error=False, description="The instance ORCHESTRATOR_TOKEN.")


def _unauthorized() -> Problem:
    """One refusal, built one way, so every 401 body is byte-identical."""
    return Problem(
        status=HTTP_UNAUTHORIZED,
        title="unauthorized",
        headers=UNAUTHORIZED_HEADERS,
    )


def get_settings(request: Request) -> Settings:
    """The settings built once by `main()`. Nothing re-reads the environment (AD-20)."""
    settings = request.app.state.settings
    if not isinstance(settings, Settings):
        raise RuntimeError(
            "app.state.settings is not a Settings: the application was not built by create_app"
        )
    return settings


def token_matches(presented: str, expected: str) -> bool:
    """The one comparison, for the one credential. Reasons: this module's docstring.

    Reused by the `/mcp` guard (`api/mcp_mount.py`), which cannot carry this dependency
    because an ASGI mount bypasses router dependencies — so it borrows the check rather than
    writing a second one.
    """
    if not expected:
        # fail closed: comparing two empty byte strings succeeds, which would open the API
        return False
    return hmac.compare_digest(presented.encode(), expected.encode())


def require_bearer(
    settings: Annotated[Settings, Depends(get_settings)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Refuse the request unless it carries the instance token, in constant time."""
    presented = credentials.credentials if credentials else ""
    if not token_matches(presented, settings.orchestrator_token.get_secret_value()):
        raise _unauthorized()
