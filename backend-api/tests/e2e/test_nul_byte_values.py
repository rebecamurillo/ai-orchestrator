"""A harness name carrying a NUL byte is a refusal, never a server error (2026-09-18).

`tests/e2e/test_schemathesis.py::test_no_operation_answers_with_a_server_error` found this
against `GET /api/v1/steps`: a PostgreSQL text field cannot hold a NUL byte, so
`attempt.harness = :harness` raised `psycopg.DataError` inside the adapter and the request
answered 500. `GET /api/v1/harnesses/{name}/readiness` compared a name the same way and
failed the same way.

The unit suite pins the shape and the two declarations
(`tests/unit/test_harness_name_pattern.py` and the two `*_shape.py` router modules) over
fakes, where no database is reachable — which is exactly what it cannot prove: that the value
stops at the edge rather than reaching psycopg. So this module states the same two requests
against the real stack, and pins them deterministically rather than leaving them to the one
draw of the fuzzer that happened to find them. It creates nothing and cleans up nothing.
"""

from __future__ import annotations

import httpx
import pytest

HTTP_UNPROCESSABLE_CONTENT = 422
PROBLEM = "application/problem+json"

#: Percent-encoded, because a NUL byte cannot travel a request line as itself.
PATHS = (
    "/api/v1/steps?harness=%00abc",
    "/api/v1/harnesses/%00abc/readiness",
)


@pytest.mark.parametrize("path", PATHS)
def test_a_nul_byte_in_a_harness_name_is_refused_not_a_server_error(
    authenticated: httpx.Client, path: str
) -> None:
    response = authenticated.get(path)

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)
