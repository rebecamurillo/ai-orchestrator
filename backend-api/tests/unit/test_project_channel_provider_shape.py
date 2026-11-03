"""Per-provider channel shape, refused at save (story 3-2 review, lead decision 2026-11-02).

The API schema is the input boundary, so it holds what each adapter can render. A Slack
mention is `<@ID>`, so an allowed user's id must be a Slack user id, and the bot token
travels only over https. A Mattermost mention is `@username`, so a handle must be a
username. Each refusal sits at its field path and is fixed text that never echoes the value.
The Mattermost id rule (26 characters of `[a-z0-9]`) is not applied: the 3-1 adapter treats
ids as opaque, and its suites use ids such as `u1` and `bot-id`.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from orchestrator.api.schemas.project_channel import ChannelIn
from tests.unit.test_project_channel_router import HTTP_UNPROCESSABLE, Harness

SLACK_ID_REASON = "a slack user id is upper-case letters and digits"
SLACK_HTTPS_REASON = "a slack base URL must use https"
MATTERMOST_HANDLE_REASON = "a mattermost handle is lower-case letters, digits, '.', '_' or '-'"


def a_body(provider: str, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": provider,
        "base_url": "https://slack.com/api" if provider == "slack" else "https://chat.test",
        "channel_id": "C0123ABC",
        "token": "tok-1",
        "allowed_users": [{"id": "U01ANA", "handle": "ana"}],
    }
    body.update(overrides)
    return body


def refusals(body: dict[str, Any]) -> dict[tuple[object, ...], str]:
    with pytest.raises(ValidationError) as caught:
        ChannelIn.model_validate(body)
    return {tuple(error["loc"]): str(error["msg"]) for error in caught.value.errors()}


# ── slack ────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("user_id", ["u01ana", "U1><!channel", "U01-ANA", "U01ANA|x", "Ü1"])
def test_a_slack_user_id_that_is_not_one_is_refused_at_its_field(user_id: str) -> None:
    users = [{"id": "U01ANA", "handle": "ana"}, {"id": user_id, "handle": "bo"}]

    found = refusals(a_body("slack", allowed_users=users))

    assert found == {("allowed_users", 1, "id"): f"Value error, {SLACK_ID_REASON}"}
    assert user_id not in repr(found)


def test_every_bad_slack_user_id_is_named() -> None:
    users = [{"id": "u1", "handle": "a"}, {"id": "U2", "handle": "b"}, {"id": "u3", "handle": "c"}]

    found = refusals(a_body("slack", allowed_users=users))

    assert set(found) == {("allowed_users", 0, "id"), ("allowed_users", 2, "id")}


@pytest.mark.parametrize("base_url", ["http://slack.com/api", "http://10.0.0.5/api"])
def test_a_slack_base_url_that_is_not_https_is_refused_at_its_field(base_url: str) -> None:
    found = refusals(a_body("slack", base_url=base_url))

    assert found == {("base_url",): f"Value error, {SLACK_HTTPS_REASON}"}
    assert base_url not in repr(found)


def test_a_slack_handle_is_not_held_to_mattermost_rules() -> None:
    users = [{"id": "U01ANA", "handle": "Ana.Lopez"}]

    assert ChannelIn.model_validate(a_body("slack", allowed_users=users)).provider == "slack"


# ── mattermost ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("handle", ["Alice", "ali+ce", "alice,bob", "ålice"])
def test_a_mattermost_handle_that_is_not_a_username_is_refused_at_its_field(handle: str) -> None:
    users = [{"id": "u1", "handle": handle}]

    found = refusals(a_body("mattermost", allowed_users=users))

    assert found == {("allowed_users", 0, "handle"): f"Value error, {MATTERMOST_HANDLE_REASON}"}
    assert handle not in repr(found)


def test_a_mattermost_channel_keeps_opaque_ids_lan_http_and_dotted_handles() -> None:
    users = [{"id": "u1", "handle": "ana.b-c_9"}, {"id": "Bot-Id", "handle": "bo"}]
    body = a_body("mattermost", base_url="http://10.0.0.5:8065", allowed_users=users)

    assert ChannelIn.model_validate(body).base_url == "http://10.0.0.5:8065"


def test_off_is_held_to_no_provider_rule() -> None:
    body = {
        "provider": "off",
        "base_url": "http://x.test",
        "allowed_users": [{"id": "u", "handle": "A"}],
    }

    assert ChannelIn.model_validate(body).provider == "off"


# ── over HTTP ────────────────────────────────────────────────────────────────


@pytest.fixture
def api(env: dict[str, str]) -> Harness:
    return Harness(env)


@pytest.mark.parametrize(
    ("body", "path", "reason"),
    [
        (
            a_body("slack", allowed_users=[{"id": "u-secretish", "handle": "a"}]),
            "body.allowed_users.0.id",
            SLACK_ID_REASON,
        ),
        (a_body("slack", base_url="http://slack.com/api"), "body.base_url", SLACK_HTTPS_REASON),
        (
            a_body("mattermost", allowed_users=[{"id": "u1", "handle": "Alice"}]),
            "body.allowed_users.0.handle",
            MATTERMOST_HANDLE_REASON,
        ),
    ],
)
async def test_a_put_is_a_422_at_the_field_and_writes_nothing(
    api: Harness, body: dict[str, Any], path: str, reason: str
) -> None:
    async with api.client() as client:
        response = await client.put(api.url(), json=body)

    assert response.status_code == HTTP_UNPROCESSABLE
    errors = {error["path"]: error["reason"] for error in response.json()["errors"]}
    assert errors == {path: f"Value error, {reason}"}
    assert "u-secretish" not in response.text
    assert api.channels.channels == {}
