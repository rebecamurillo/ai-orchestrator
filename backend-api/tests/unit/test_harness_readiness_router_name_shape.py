"""`/api/v1/harnesses/{name}/readiness` refuses a name no harness can have (2026-09-18).

`GET` reads the row by name — `harness.name = :name` over Postgres — and a PostgreSQL text
field cannot hold a NUL byte, so a name carrying one raised `psycopg.DataError` in the
repository and answered 500. It is the same defect
`tests/unit/test_history_router_harness_shape.py` pins on `GET /steps?harness=`, on the other
parameter that carries a harness name, and the same one
`tests/e2e/test_schemathesis.py::test_no_operation_answers_with_a_server_error` exists to
catch.

`start` already refuses an unknown *name* (`HARNESS_NAMES`, 404), which is a narrower set
than this path may serve: the `fake` harness `ORCH_TEST_MODE` seeds is a row with a real name
outside that tuple, and `GET` must keep answering for it. What the path declares instead is
the *shape* (`domain/entities/harness.py::HARNESS_NAME_PATTERN`) — which is what
`BAD_NAME_RESPONSE`, "`name` does not match the shape below", has always said it published —
so a malformed name is Pydantic's own 422 in this API's problem document and no repository is
read.

The 201, the 404s and the 409 are `tests/unit/test_harness_readiness_router.py`'s; its `Api`
harness is imported rather than rebuilt.
"""

from __future__ import annotations

import pytest

from orchestrator.api.providers import harness_ports
from orchestrator.application.use_cases.harnesses import HarnessPorts
from orchestrator.domain.entities.harness import Harness
from tests.unit.fakes.harnesses import FakeHarnessRepository
from tests.unit.test_harness_readiness_router import HTTP_OK, Api

HTTP_UNPROCESSABLE_CONTENT = 422
PROBLEM = "application/problem+json"

#: The name schemathesis reached the database with, percent-encoded as it travels.
NUL_NAME = "%00x"
READINESS = "/api/v1/harnesses/{name}/readiness"
#: A harness with a real row and a real name that `HARNESS_NAMES` does not list (AR-14).
FAKE = Harness(name="fake", enabled=True, version_pin="0")


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    api = Api(env)
    api.app.dependency_overrides[harness_ports] = lambda: HarnessPorts(
        uow=api.uow, harnesses=FakeHarnessRepository([FAKE])
    )
    return api


async def test_reading_a_name_carrying_a_nul_byte_is_refused(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(READINESS.format(name=NUL_NAME))

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_dispatching_against_a_name_carrying_a_nul_byte_is_refused(api: Api) -> None:
    async with api.client() as client:
        response = await client.post(READINESS.format(name=NUL_NAME))

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_a_well_shaped_name_outside_harness_names_is_still_read(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(READINESS.format(name="fake"))

    assert response.status_code == HTTP_OK
    assert response.json()["name"] == "fake"


async def test_the_contract_publishes_the_shape(api: Api) -> None:
    """AD-3: the shape the declared 422 names is in the document, not only in the prose."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    operations = document["paths"]["/api/v1/harnesses/{name}/readiness"]
    for method in ("get", "post"):
        name = next(
            parameter
            for parameter in operations[method]["parameters"]
            if parameter["name"] == "name"
        )
        assert "pattern" in name["schema"]
