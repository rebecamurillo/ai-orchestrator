"""`domain/entities/project_channel.py` — the stored channel, its read model and its shape rules."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from orchestrator.domain.entities.project_channel import (
    ProjectChannel,
    ProjectChannelView,
    is_valid_base_url,
    is_valid_channel_id,
    is_valid_handle,
    is_valid_user_id,
)
from orchestrator.domain.ids import new_id
from orchestrator.domain.ports.chat import ChatUser

AT = datetime(2026, 11, 2, tzinfo=UTC)
CIPHERTEXT = "fake-enc:1:c2VjcmV0"


def a_channel() -> ProjectChannel:
    return ProjectChannel(
        project_id=new_id(),
        provider="mattermost",
        base_url="https://chat.example.com",
        channel_id="c1",
        token_enc=CIPHERTEXT,
        allowed_users=(ChatUser(id="u1", handle="alice"),),
        metadata_only=True,
        created_at=AT,
        updated_at=AT,
    )


def test_the_view_drops_the_ciphertext_and_says_a_token_is_set() -> None:
    view = a_channel().view()

    assert view == ProjectChannelView(
        provider="mattermost",
        base_url="https://chat.example.com",
        channel_id="c1",
        token_set=True,
        allowed_users=(ChatUser(id="u1", handle="alice"),),
        metadata_only=True,
    )


def test_the_stored_channels_repr_omits_the_ciphertext() -> None:
    assert CIPHERTEXT not in repr(a_channel())


def test_off_is_the_view_of_no_row() -> None:
    off = ProjectChannelView.off()

    assert (off.provider, off.base_url, off.channel_id) == ("off", None, None)
    assert (off.token_set, off.allowed_users, off.metadata_only) == (False, (), False)


@pytest.mark.parametrize(
    "url",
    ["https://chat.example.com", "http://127.0.0.1:9", "https://chat.example.com/mm/"],
)
def test_an_http_url_with_a_host_is_a_base_url(url: str) -> None:
    assert is_valid_base_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "chat.example.com",
        "ftp://chat.example.com",
        "https://",
        "https:///path",
        "https://chat .example.com",
        "https://chat.example.com:notaport",
        "javascript:alert(1)",
    ],
)
def test_anything_else_is_not(url: str) -> None:
    assert not is_valid_base_url(url)


@pytest.mark.parametrize(("value", "valid"), [("c1", True), ("", False), ("c 1", False)])
def test_a_channel_id_is_non_empty_without_whitespace(value: str, valid: bool) -> None:
    assert is_valid_channel_id(value) is valid


@pytest.mark.parametrize(("value", "valid"), [("u1", True), ("", False), ("u\t1", False)])
def test_a_user_id_is_non_empty_without_whitespace(value: str, valid: bool) -> None:
    assert is_valid_user_id(value) is valid


@pytest.mark.parametrize(
    ("value", "valid"),
    [("alice", True), ("a.b-c_d", True), ("", False), ("@alice", False), ("al ice", False)],
)
def test_a_handle_has_no_at_sign_and_no_whitespace(value: str, valid: bool) -> None:
    assert is_valid_handle(value) is valid
