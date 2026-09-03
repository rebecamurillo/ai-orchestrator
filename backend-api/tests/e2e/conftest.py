"""What the e2e suite needs from the environment, and the clients it hands to tests.

Two variables, both already in the `.env.example` contract: `BACKEND_API_URL` (declared for
the web-client, allowlisted for compose) and `ORCHESTRATOR_TOKEN`. Nothing here invents a
setting, and no token value is ever printed — a failure names the variable, not its value.

Nothing here ever skips. An e2e gate that skips when the stack is missing reports success
for a suite that ran nothing; every fixture below fails instead, with a message naming what
is wrong. The readiness poll exists for the unattended case — a gate started beside a stack
that is still coming up must wait for it, not report connection-refused as a test failure —
and it too fails, loudly, when its deadline passes.

The default URL is the compose service name, which is what a run from inside the stack
sees. From a shell on the host, point it at the published port:

    BACKEND_API_URL=http://127.0.0.1:8000 make e2e-api
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator

import httpx
import pytest

DEFAULT_BASE_URL = "http://backend-api:8000"
TIMEOUT_SECONDS = 10.0

#: How long a stack may take to come up before the gate calls it down.
READINESS_TIMEOUT_SECONDS = 30.0
READINESS_INTERVAL_SECONDS = 0.5

HTTP_OK = 200


def require(variable: str) -> str:
    """Read a required variable, failing with its name and never with its value."""
    value = os.environ.get(variable)
    if not value:
        pytest.fail(
            f"{variable} is not set: the e2e gate runs against a configured stack "
            "(`cp .env.example .env`, fill it in, and export it)"
        )
    return value


def resolve_base_url() -> str:
    """The stack's address. Read at import time too, by the schema loader."""
    return os.environ.get("BACKEND_API_URL", DEFAULT_BASE_URL).rstrip("/")


@pytest.fixture(scope="session")
def base_url() -> str:
    return resolve_base_url()


@pytest.fixture(scope="session")
def token() -> str:
    return require("ORCHESTRATOR_TOKEN")


@pytest.fixture(scope="session")
def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def stack(base_url: str) -> str:
    """Wait for `/healthz` to answer, then hand back the base URL every client uses.

    Bounded and failing: a stack that never comes up is reported as one, with the address
    that was tried and the deadline that passed.
    """
    deadline = time.monotonic() + READINESS_TIMEOUT_SECONDS
    last: str = "no attempt completed"
    with httpx.Client(base_url=base_url, timeout=TIMEOUT_SECONDS) as client:
        while time.monotonic() < deadline:
            try:
                response = client.get("/healthz")
            except httpx.HTTPError as error:
                last = f"{type(error).__name__}: {error}"
            else:
                if response.status_code == HTTP_OK:
                    return base_url
                last = f"/healthz answered {response.status_code}"
            time.sleep(READINESS_INTERVAL_SECONDS)

    pytest.fail(
        f"backend-api at {base_url} was not ready within "
        f"{READINESS_TIMEOUT_SECONDS:.0f}s — last attempt: {last}"
    )


@pytest.fixture
def client(stack: str) -> Iterator[httpx.Client]:
    """A client carrying no credential — the shape most of the 401 scenarios need."""
    with httpx.Client(base_url=stack, timeout=TIMEOUT_SECONDS) as client:
        yield client


@pytest.fixture
def authenticated(stack: str, bearer: dict[str, str]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=stack, headers=bearer, timeout=TIMEOUT_SECONDS) as client:
        yield client
