"""Every operation the contract publishes, driven with generated input.

Schemathesis reads `/openapi.json` from the running process and calls each operation with
data derived from the schema. The property asserted is the one the story states: no request
it can build produces a 5xx.

The schema is loaded from a fixture, not at import. Loading it at module scope would put an
HTTP request in pytest's collection phase — so a stack that is down would produce a
connection traceback from the loader instead of the message `conftest` was written to give,
and a bare `pytest` inside `backend-api` (where `testpaths = ["tests"]`) would reach the
network just to collect. The fixture depends on `stack`, so the readiness poll runs first
and a stack that never comes up fails the gate rather than skipping it.

Only `not_a_server_error` is run. The v4 default set also checks schema and data
conformance, and every generated call currently answers 401 — a status whose exact body is
not yet pinned in the contract — so those checks would fail on correct behaviour and make an
unattended gate flaky. The story that adds declared response models can widen this list.
"""

from __future__ import annotations

import pytest
import schemathesis
from schemathesis import Case

from tests.e2e.conftest import require

CHECKS = (schemathesis.checks.not_a_server_error,)


@pytest.fixture(scope="session")
def api_schema(stack: str) -> schemathesis.BaseSchema:
    """The published contract, read from the running process once the stack answers."""
    return schemathesis.openapi.from_url(f"{stack}/openapi.json")


@pytest.fixture(scope="module")
def authorization() -> dict[str, str]:
    return {"Authorization": f"Bearer {require('ORCHESTRATOR_TOKEN')}"}


schema = schemathesis.pytest.from_fixture("api_schema")


@schema.parametrize()
def test_no_operation_answers_with_a_server_error(
    case: Case, authorization: dict[str, str]
) -> None:
    case.call_and_validate(headers=authorization, checks=CHECKS)
