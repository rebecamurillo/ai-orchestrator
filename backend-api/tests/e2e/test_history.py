"""`GET /api/v1/steps` against the real stack (SPEC CAP-5, FR-25 history).

The join, the paging and the filters are settled without a database by
`tests/unit/application/test_history.py` and `tests/unit/test_history_repository_adapter.py`.
What only Postgres can settle is that the *statement* runs: the four-table join, `status IN
(...)`, and above all the keyset window — `(started_at, id) < (:started_at, :id)` is a row
comparison, a construct a recording session double can only prove was built, never that the
server accepts it against a `timestamptz` and a `uuid` together.

So this module reads the endpoint rather than staging a Run. Every scenario is shape-based
and count-free: this gate shares one stack with modules that create Runs, so the history is
never empty on purpose and never the same length twice. It creates nothing and cleans up
nothing, because it writes nothing.
"""

from __future__ import annotations

from base64 import urlsafe_b64encode
from uuid import uuid4

import httpx

HTTP_OK = 200
HTTP_UNPROCESSABLE_CONTENT = 422
PROBLEM = "application/problem+json"
STEPS = "/api/v1/steps"

#: Every token the bar offers (`application/use_cases/history.py::STATUS_FILTERS`).
TOKENS = ("QUE", "RUN", "BLK", "ERR", "DON")

ROW_FIELDS = frozenset(
    {
        "attempt_id",
        "run_id",
        "seq",
        "started_at",
        "ended_at",
        "seconds",
        "project_name",
        "run_label",
        "path",
        "kind",
        "harness",
        "model",
        "session_id",
        "status",
        "token",
        "tokens_in",
        "tokens_out",
        "cost_usd",
        "cost_provisional",
        "trace_url",
        "log_tail_url",
    }
)


def a_cursor() -> str:
    """A well-formed cursor onto a moment before this system existed: the window is what is
    under test, not what falls inside it."""
    return urlsafe_b64encode(f"2020-01-01T00:00:00+00:00|{uuid4()}".encode()).decode()


def test_the_endpoint_answers_the_one_list_envelope(authenticated: httpx.Client) -> None:
    response = authenticated.get(STEPS)

    assert response.status_code == HTTP_OK
    body = response.json()
    assert sorted(body) == ["items", "next_cursor"]
    assert isinstance(body["items"], list)


def test_every_row_carries_exactly_the_fields_the_table_prints(authenticated: httpx.Client) -> None:
    body = authenticated.get(STEPS, params={"limit": 5}).json()

    for row in body["items"]:
        assert set(row) == ROW_FIELDS


def test_the_keyset_window_is_a_row_comparison_postgres_accepts(
    authenticated: httpx.Client,
) -> None:
    response = authenticated.get(STEPS, params={"cursor": a_cursor(), "limit": 5})

    assert response.status_code == HTTP_OK
    # the cursor names 2020: nothing in this system started before it
    assert response.json()["items"] == []


def test_every_status_token_runs_as_an_in_predicate(authenticated: httpx.Client) -> None:
    for token in TOKENS:
        response = authenticated.get(STEPS, params={"status": token})

        assert response.status_code == HTTP_OK, token


def test_the_project_and_harness_filters_run(authenticated: httpx.Client) -> None:
    response = authenticated.get(
        STEPS, params={"project_id": str(uuid4()), "harness": "codex", "limit": 5}
    )

    assert response.status_code == HTTP_OK
    assert response.json()["items"] == []


def test_an_unknown_status_token_is_a_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(STEPS, params={"status": "NOPE"})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


def test_an_unreadable_cursor_is_a_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(STEPS, params={"cursor": "not-a-cursor"})

    assert response.status_code == HTTP_UNPROCESSABLE_CONTENT
    assert response.headers["content-type"].startswith(PROBLEM)


def test_a_limit_outside_the_bounds_is_refused(authenticated: httpx.Client) -> None:
    for limit in (0, 5000):
        response = authenticated.get(STEPS, params={"limit": limit})

        assert response.status_code == HTTP_UNPROCESSABLE_CONTENT, limit


def test_an_unauthenticated_read_is_refused(client: httpx.Client) -> None:
    assert client.get(STEPS).status_code == httpx.codes.UNAUTHORIZED
