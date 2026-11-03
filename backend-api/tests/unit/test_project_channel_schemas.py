"""`api/schemas/project_channel.py` — the channel's HTTP shape (story 3-4).

Every refusal names its field, and no refusal, repr or serialisation carries the token.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from orchestrator.api.schemas.project_channel import ChannelIn, ChannelOut, ChannelTestOut
from orchestrator.domain.entities.project_channel import ProjectChannelView
from orchestrator.domain.ports.chat import ChatUser


def a_token() -> str:
    return f"tok-{uuid4()}"


def a_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "provider": "mattermost",
        "base_url": "https://chat.example.com",
        "channel_id": "c1",
        "token": a_token(),
        "allowed_users": [{"id": "u1", "handle": "alice"}],
    }
    body.update(overrides)
    return body


def refusal(body: dict[str, Any]) -> list[dict[str, Any]]:
    with pytest.raises(ValidationError) as caught:
        ChannelIn.model_validate(body)
    return caught.value.errors()


def locations(body: dict[str, Any]) -> set[tuple[object, ...]]:
    return {tuple(error["loc"]) for error in refusal(body)}


# ── accepted ─────────────────────────────────────────────────────────────────


def test_a_full_mattermost_body_becomes_a_draft() -> None:
    token = a_token()

    draft = ChannelIn.model_validate(a_body(token=token, metadata_only=True)).as_draft()

    assert draft.provider == "mattermost"
    assert draft.base_url == "https://chat.example.com"
    assert draft.channel_id == "c1"
    assert draft.token == token
    assert draft.allowed_users == (ChatUser(id="u1", handle="alice"),)
    assert draft.metadata_only is True


def test_a_body_without_a_token_drafts_a_keep() -> None:
    body = a_body()
    del body["token"]

    assert ChannelIn.model_validate(body).as_draft().token is None


def test_off_needs_nothing_else() -> None:
    draft = ChannelIn.model_validate({"provider": "off"}).as_draft()

    assert draft.provider == "off"
    assert (draft.base_url, draft.channel_id, draft.allowed_users) == (None, None, ())
    assert draft.metadata_only is False


def test_the_token_is_a_secret_the_payload_never_renders() -> None:
    token = a_token()
    payload = ChannelIn.model_validate(a_body(token=token))

    assert isinstance(payload.token, SecretStr)
    assert token not in repr(payload)
    assert token not in str(payload)
    assert token not in payload.model_dump_json()


# ── refused, field named ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"base_url": "ftp://chat.example.com"}, ("base_url",)),
        ({"base_url": "https://"}, ("base_url",)),
        ({"base_url": None}, ("base_url",)),
        ({"channel_id": ""}, ("channel_id",)),
        ({"channel_id": None}, ("channel_id",)),
        ({"allowed_users": []}, ("allowed_users",)),
        (
            {"allowed_users": [{"id": "u1", "handle": "a"}, {"id": "u1", "handle": "b"}]},
            ("allowed_users",),
        ),
        ({"allowed_users": [{"id": "u1", "handle": "@alice"}]}, ("allowed_users", 0, "handle")),
        ({"allowed_users": [{"id": "u1", "handle": "al ice"}]}, ("allowed_users", 0, "handle")),
        ({"allowed_users": [{"id": "", "handle": "alice"}]}, ("allowed_users", 0, "id")),
        # Story 3-2, 2026-11-02 (hard rule 1(b)): `slack` is now accepted (see
        # test_project_channel_slack.py); an unknown provider is still refused here.
        ({"provider": "teams"}, ("provider",)),
        ({"base_url": "https://chat.example.com/\x00"}, ("base_url",)),
    ],
)
def test_a_bad_shape_is_refused_at_its_field(overrides: dict[str, Any], loc: tuple) -> None:
    assert loc in locations(a_body(**overrides))


def test_a_missing_base_url_on_mattermost_is_refused_at_the_field() -> None:
    body = a_body()
    del body["base_url"]
    del body["channel_id"]

    assert {("base_url",), ("channel_id",)} <= locations(body)


@pytest.mark.parametrize("token", ["", "tok with space", "tok\nline", "tök-ünicode"])
def test_a_malformed_token_is_refused_without_echoing_it(token: str) -> None:
    errors = refusal(a_body(token=token))

    assert [tuple(error["loc"]) for error in errors] == [("token",)]
    if token:
        assert all(token not in str(error["msg"]) for error in errors)


def test_no_validator_message_echoes_a_token_anywhere() -> None:
    token = a_token()

    errors = refusal(a_body(token=token, base_url="nope", allowed_users=[]))

    assert all(token not in str(error["msg"]) for error in errors)


# ── out ──────────────────────────────────────────────────────────────────────


def test_the_read_model_carries_token_set_and_no_token_field() -> None:
    view = ProjectChannelView(
        provider="mattermost",
        base_url="https://chat.example.com",
        channel_id="c1",
        token_set=True,
        allowed_users=(ChatUser(id="u1", handle="alice"),),
        metadata_only=False,
    )

    out = ChannelOut.of(view).model_dump(mode="json")

    assert out == {
        "provider": "mattermost",
        "base_url": "https://chat.example.com",
        "channel_id": "c1",
        "token_set": True,
        "allowed_users": [{"id": "u1", "handle": "alice"}],
        "metadata_only": False,
    }
    assert "token" not in ChannelOut.model_fields


def test_off_reads_with_nulls_and_an_empty_list() -> None:
    out = ChannelOut.of(ProjectChannelView.off()).model_dump(mode="json")

    assert out == {
        "provider": "off",
        "base_url": None,
        "channel_id": None,
        "token_set": False,
        "allowed_users": [],
        "metadata_only": False,
    }


def test_the_test_result_is_ok_and_detail() -> None:
    assert ChannelTestOut(ok=False, detail="401 no").model_dump() == {
        "ok": False,
        "detail": "401 no",
    }
