"""A Project's chat channel against the running stack (story 3-4).

The unit suite proves the rules over fakes. What only the stack settles: the row survives a
real schema, the kept ciphertext is byte-identical, the token reaches no response body, and
the real Mattermost adapter answers a dead host as `ok: false` rather than a 5xx.

Port 9 (discard) on loopback is closed in the backend container, so the probe fails with a
connection error and never reaches a chat platform.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text

from orchestrator.infrastructure.db import create_engine_from
from orchestrator.infrastructure.settings import Settings

HTTP_OK = 200
HTTP_CREATED = 201
HTTP_NOT_FOUND = 404
HTTP_CONFLICT = 409
HTTP_UNPROCESSABLE = 422
PROJECTS = "/api/v1/projects"
UNKNOWN_ID = "01a06887-79ab-759b-97a0-71c32ad939c2"
DEAD_HOST = "http://127.0.0.1:9"


@pytest.fixture
def project_id(authenticated: httpx.Client) -> str:
    response = authenticated.post(PROJECTS, json={"name": f"e2e channel {uuid4()}"})
    assert response.status_code == HTTP_CREATED, response.text
    identifier: str = response.json()["id"]
    return identifier


def channel_url(project_id: str, suffix: str = "") -> str:
    return f"{PROJECTS}/{project_id}/channel{suffix}"


def a_body(token: str | None, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "mattermost",
        "base_url": DEAD_HOST,
        "channel_id": "town-square",
        "allowed_users": [{"id": "u1", "handle": "alice"}],
        "metadata_only": False,
    }
    if token is not None:
        body["token"] = token
    body.update(overrides)
    return body


def stored_ciphertext(project_id: str) -> str | None:
    engine = create_engine_from(Settings())
    try:
        with engine.connect() as connection:
            value = connection.execute(
                text("SELECT token_enc FROM project_channel WHERE project_id = :id"),
                {"id": project_id},
            ).scalar_one_or_none()
    finally:
        engine.dispose()
    return value


def test_a_new_project_reads_off(authenticated: httpx.Client, project_id: str) -> None:
    response = authenticated.get(channel_url(project_id))

    assert response.status_code == HTTP_OK
    assert response.json() == {
        "provider": "off",
        "base_url": None,
        "channel_id": None,
        "token_set": False,
        "allowed_users": [],
        "metadata_only": False,
    }


def test_save_read_keep_test_and_off(authenticated: httpx.Client, project_id: str) -> None:
    token = f"tok-{uuid4()}"

    saved = authenticated.put(channel_url(project_id), json=a_body(token))
    assert saved.status_code == HTTP_OK, saved.text
    assert saved.json()["token_set"] is True
    ciphertext = stored_ciphertext(project_id)
    assert ciphertext is not None
    assert token not in ciphertext

    kept = authenticated.put(channel_url(project_id), json=a_body(None, channel_id="off-topic"))
    assert kept.status_code == HTTP_OK, kept.text
    assert kept.json()["channel_id"] == "off-topic"
    assert stored_ciphertext(project_id) == ciphertext

    probe = authenticated.post(channel_url(project_id, "/test"))
    assert probe.status_code == HTTP_OK, probe.text
    assert probe.json()["ok"] is False
    assert probe.json()["detail"]

    reads = [
        authenticated.get(PROJECTS),
        authenticated.get(f"{PROJECTS}/{project_id}"),
        authenticated.get(channel_url(project_id)),
        probe,
    ]
    for response in reads:
        assert response.status_code == HTTP_OK
        assert token not in response.text

    off = authenticated.put(channel_url(project_id), json={"provider": "off"})
    assert off.status_code == HTTP_OK
    assert off.json()["provider"] == "off"
    assert stored_ciphertext(project_id) is None
    again = authenticated.put(channel_url(project_id), json={"provider": "off"})
    assert again.status_code == HTTP_OK


def test_a_keep_with_nothing_stored_is_refused(
    authenticated: httpx.Client, project_id: str
) -> None:
    response = authenticated.put(channel_url(project_id), json=a_body(None))

    assert response.status_code == HTTP_UNPROCESSABLE
    assert response.json()["detail"] == "token: no stored token to keep"


def test_a_test_with_no_channel_is_a_conflict(authenticated: httpx.Client, project_id: str) -> None:
    response = authenticated.post(channel_url(project_id, "/test"))

    assert response.status_code == HTTP_CONFLICT


def test_the_builtin_project_refuses_a_channel(authenticated: httpx.Client) -> None:
    projects = authenticated.get(PROJECTS).json()["items"]
    builtin = next(project for project in projects if project["builtin"])

    response = authenticated.put(channel_url(builtin["id"]), json={"provider": "off"})

    assert response.status_code == HTTP_CONFLICT


def test_an_unknown_project_is_a_404(authenticated: httpx.Client) -> None:
    assert authenticated.get(channel_url(UNKNOWN_ID)).status_code == HTTP_NOT_FOUND
