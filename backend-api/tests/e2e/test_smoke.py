"""The scenarios that only a running stack can prove.

The unit suite already asserts the 401 bodies over an in-process transport. What it cannot
assert is that the deployed process behaves the same: that the public healthcheck answers
without a credential, and that the bearer the operator put in `.env` is the one the running
server compares against. That the migration ran is a separate claim, settled against the
database in `tests/e2e/test_migrations.py`.
"""

from __future__ import annotations

import httpx

HTTP_OK = 200
HTTP_UNAUTHORIZED = 401
HTTP_NOT_FOUND = 404

PROBLEM_MEDIA_TYPE = "application/problem+json"
API_PREFIX = "/api/v1"


# ── public surface ───────────────────────────────────────────────────────────


def test_healthz_answers_without_a_credential(client: httpx.Client) -> None:
    response = client.get("/healthz")

    assert response.status_code == HTTP_OK
    assert response.json()["status"] == "ok"


def test_the_contract_document_is_public(client: httpx.Client) -> None:
    """1.3 exports this document; it must be readable without the token."""
    response = client.get("/openapi.json")

    assert response.status_code == HTTP_OK
    assert "/healthz" in response.json()["paths"]
    assert f"{API_PREFIX}/ping" in response.json()["paths"]


# ── the credential ───────────────────────────────────────────────────────────


def test_a_versioned_route_refuses_a_request_with_no_header(client: httpx.Client) -> None:
    response = client.get(f"{API_PREFIX}/ping")

    assert response.status_code == HTTP_UNAUTHORIZED
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "unauthorized"


def test_a_wrong_token_is_refused_with_the_same_body(client: httpx.Client) -> None:
    missing = client.get(f"{API_PREFIX}/ping")
    wrong = client.get(
        f"{API_PREFIX}/ping", headers={"Authorization": "Bearer not-the-instance-token"}
    )

    assert wrong.status_code == HTTP_UNAUTHORIZED
    assert wrong.content == missing.content


def test_a_junk_header_is_refused_rather_than_crashing(client: httpx.Client) -> None:
    """A non-ASCII credential must be a 401; a 500 here would be a `compare_digest` bug."""
    response = client.get(
        f"{API_PREFIX}/ping", headers={"Authorization": "Bearer ünicode".encode("latin-1")}
    )

    assert response.status_code == HTTP_UNAUTHORIZED


def test_ping_answers_with_the_configured_token(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{API_PREFIX}/ping")

    assert response.status_code == HTTP_OK
    assert response.json() == {"pong": True}


def test_the_refusal_never_echoes_the_token(client: httpx.Client, token: str) -> None:
    response = client.get(f"{API_PREFIX}/ping", headers={"Authorization": f"Bearer {token}x"})

    assert response.status_code == HTTP_UNAUTHORIZED
    assert token not in response.text


# ── the error shape, from the deployed process ───────────────────────────────


def test_an_unknown_versioned_path_is_a_problem_document(authenticated: httpx.Client) -> None:
    response = authenticated.get(f"{API_PREFIX}/nope")

    assert response.status_code == HTTP_NOT_FOUND
    assert response.headers["content-type"].startswith(PROBLEM_MEDIA_TYPE)
    assert response.json()["title"] == "not found"


def test_the_problem_document_carries_only_declared_members(client: httpx.Client) -> None:
    body = client.get(f"{API_PREFIX}/ping").json()

    assert set(body) <= {"type", "title", "status", "detail", "instance", "errors"}
