"""`MattermostChannel` hardening from the story 3-1 review (2026-11-02).

Covers tokens that cannot be sent, request-building failures, integration posts, page and
size caps, and cookies, which would otherwise be shared between bots on one client.
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from orchestrator.domain.ports.chat import ChatError, ThreadRef
from orchestrator.infrastructure.chat.mattermost import (
    MAX_PAGES,
    MAX_RESPONSE_BYTES,
    MattermostChannel,
)

BASE = "https://chat.example.test"
ME = {"id": "bot-id", "username": "bot"}
ROOT = ThreadRef(id="root")


def a_client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def me_only(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json=ME)


def assert_hidden(error: ChatError, *secrets: str) -> None:
    for secret in secrets:
        for text in (error.detail, str(error), repr(error), repr(error.args)):
            assert secret not in text


@pytest.mark.parametrize(
    "token",
    ["sekrit-tok\n", "sekrit tok", "sekrït-tok", "\tsekrit", "sekrit\x00tok", ""],
)
def test_a_token_that_cannot_be_sent_is_refused_without_echoing_it(token: str) -> None:
    with capture_logs() as logs, pytest.raises(ChatError) as caught:
        MattermostChannel(BASE, "ch1", token, client=a_client(me_only))

    assert caught.value.detail == "the token must be non-empty printable ASCII with no whitespace"
    assert caught.value.__cause__ is None
    if token.strip():
        assert_hidden(caught.value, token, token.strip(), repr(token)[1:-1])
    assert logs == []


@pytest.mark.parametrize(
    ("base_url", "kind"),
    [("https://[::1", "InvalidURL"), ("://", "ValueError")],
)
def test_a_request_that_cannot_be_built_is_a_chat_error_without_its_message(
    base_url: str, kind: str
) -> None:
    token = "sekrit-tok"
    channel = MattermostChannel(base_url, "ch1", token, client=a_client(me_only))

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == f"{kind}: the request to /api/v4/users/me could not be built"
    assert caught.value.__cause__ is None
    assert_hidden(caught.value, token)


def test_a_unicode_error_while_sending_is_a_chat_error_without_its_message() -> None:
    token = "sekrit-tok"

    def explode(request: httpx.Request) -> httpx.Response:
        raise UnicodeEncodeError("ascii", f"Bearer {token}", 7, 8, "ordinal not in range")

    channel = MattermostChannel(BASE, "ch1", token, client=a_client(explode))

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail.startswith("UnicodeEncodeError: the request to")
    assert_hidden(caught.value, token)


def test_an_escaped_token_in_a_transport_error_is_redacted_too() -> None:
    token = r"sekrit\tok"
    escaped = repr(f"Bearer {token}".encode())

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.LocalProtocolError(f"Illegal header value {escaped}")

    channel = MattermostChannel(BASE, "ch1", token, client=a_client(refuse))

    with capture_logs() as logs, pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "LocalProtocolError: Illegal header value b'Bearer ***'"
    assert_hidden(caught.value, token, repr(token)[1:-1])
    assert logs == []


def a_post(n: int, props: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": f"p{n:02d}",
        "create_at": 2000 + n,
        "user_id": "u1",
        "root_id": "root",
        "message": "@bot hi",
        "type": "",
        "props": props,
    }


def one_page(posts: list[dict[str, Any]]) -> MattermostChannel:
    page = {"order": [p["id"] for p in posts], "posts": {p["id"]: p for p in posts}}
    return MattermostChannel(
        BASE,
        "ch1",
        "tok",
        client=a_client(
            lambda r: httpx.Response(200, json=ME if r.url.path.endswith("/me") else page)
        ),
    )


@pytest.mark.parametrize(
    "props",
    [
        {"from_webhook": "TRUE"},
        {"from_webhook": "True"},
        {"from_bot": 1},
        {"from_plugin": 0},
        {"from_plugin": "yes"},
        {"from_webhook": " false"},
        {"from_bot": []},
        {"override_username": "Ana"},
        {"override_icon_url": "https://evil.example.test/ana.png"},
        {"override_username": ""},
    ],
)
def test_a_post_with_any_integration_mark_is_not_a_reply(props: dict[str, Any]) -> None:
    assert one_page([a_post(1, props)]).replies_since(ROOT, None) == []


@pytest.mark.parametrize(
    "props",
    [
        {},
        {"from_webhook": ""},
        {"from_bot": "false"},
        {"from_plugin": "FALSE"},
        {"from_bot": False},
    ],
)
def test_a_post_without_an_integration_mark_is_a_reply(props: dict[str, Any]) -> None:
    assert [r.id for r in one_page([a_post(1, props)]).replies_since(ROOT, None)] == ["p01"]


def test_a_thread_longer_than_the_page_cap_is_refused() -> None:
    reads: list[httpx.Request] = []

    def endless(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/me"):
            return httpx.Response(200, json=ME)
        reads.append(request)
        post = a_post(len(reads), {})
        return httpx.Response(
            200, json={"order": [post["id"]], "posts": {post["id"]: post}, "has_next": True}
        )

    channel = MattermostChannel(BASE, "ch1", "tok", client=a_client(endless))

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ROOT, None)

    assert caught.value.detail == f"/api/v4/posts/root/thread has more than {MAX_PAGES} pages"
    assert len(reads) == MAX_PAGES


def test_an_answer_larger_than_the_size_cap_is_refused() -> None:
    huge = b"x" * (MAX_RESPONSE_BYTES + 1)
    channel = MattermostChannel(
        BASE, "ch1", "tok", client=a_client(lambda _: httpx.Response(200, content=huge))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == f"/api/v4/users/me answered more than {MAX_RESPONSE_BYTES} bytes"


def test_an_answer_at_the_size_cap_is_read() -> None:
    body = b'{"id": "bot-id", "username": "bot"}'
    padded = body + b" " * (MAX_RESPONSE_BYTES - len(body))
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=padded)

    channel = MattermostChannel(BASE, "ch1", "tok", client=a_client(respond))

    assert channel.probe() == "bot"


def test_the_default_client_keeps_no_cookies() -> None:
    channel = MattermostChannel(BASE, "ch1", "tok")
    jar = channel._client.cookies.jar

    request = httpx.Request("GET", f"{BASE}/api/v4/users/me")
    channel._client.cookies.extract_cookies(
        httpx.Response(200, headers={"Set-Cookie": "MMAUTHTOKEN=other; Path=/"}, request=request)
    )

    assert list(jar) == []
    assert re.search("MMAUTHTOKEN", str(channel._client.cookies)) is None
