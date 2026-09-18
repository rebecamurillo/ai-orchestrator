"""`GET /api/v1/steps?harness=…` refuses a value no harness name can be (2026-09-18).

`harness` is a free-text filter — the `fake` harness `ORCH_TEST_MODE` seeds is a real name
outside `HARNESS_NAMES`, so the filter cannot be a membership check — and it reaches
Postgres as `attempt.harness = :harness`. A PostgreSQL text field cannot hold a NUL byte, so
a filter carrying one raised `psycopg.DataError` inside the adapter and answered 500: the
failure `tests/e2e/test_schemathesis.py::test_no_operation_answers_with_a_server_error` found
on `GET /api/v1/steps`.

The router declares the shape (`domain/entities/harness.py::HARNESS_NAME_PATTERN`,
pinned by `tests/unit/test_harness_name_pattern.py`), so the refusal is Pydantic's own 422 in
this API's problem document, and the query is never built. The rest of this route —
envelope, paging, filters, the two other refusals — is `tests/unit/test_history_router.py`'s;
its `Api` harness is imported rather than rebuilt.
"""

from __future__ import annotations

import pytest

from tests.unit.test_history_router import (
    HTTP_OK,
    HTTP_UNPROCESSABLE_CONTENT,
    PROBLEM,
    STEPS,
    Api,
)

#: What schemathesis sent, reduced to the byte that made the difference.
NUL_HARNESS = "\x00abc"


@pytest.fixture
def api(env: dict[str, str]) -> Api:
    return Api(env)


async def test_a_harness_filter_carrying_a_nul_byte_is_refused(api: Api) -> None:
    async with api.client() as client:
        response = await client.get(STEPS, params={"harness": NUL_HARNESS})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


async def test_the_refusal_happens_before_the_query_is_asked(api: Api) -> None:
    async with api.client() as client:
        await client.get(STEPS, params={"harness": NUL_HARNESS})

    assert api.query.calls == []


async def test_a_well_shaped_name_outside_harness_names_still_filters(api: Api) -> None:
    """The `fake` harness (AR-14) is a name this endpoint must keep answering for."""
    async with api.client() as client:
        response = await client.get(STEPS, params={"harness": "fake"})

    assert response.status_code == HTTP_OK
    assert api.query.calls[-1].harness == "fake"


async def test_the_contract_publishes_the_shape(api: Api) -> None:
    """AD-3: the browser's types come from this document, so the bound is declared, not
    implicit in a handler."""
    async with api.client() as client:
        document = (await client.get("/openapi.json")).json()

    parameters = document["paths"]["/api/v1/steps"]["get"]["parameters"]
    harness = next(parameter for parameter in parameters if parameter["name"] == "harness")
    assert any("pattern" in option for option in harness["schema"]["anyOf"])
