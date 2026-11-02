"""`SlackChannel` hardening (story 3-2): the token stays secret, and every read is bounded.

The bot token is sent only as `Authorization: Bearer` to the configured host. Every way it
could come back, in an error body, a transport error or a refused construction, shows `***`.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from structlog.testing import capture_logs

from orchestrator.domain.ports.chat import ChatError, ThreadRef
from orchestrator.infrastructure.chat.http import MAX_RESPONSE_BYTES, TOKEN_REFUSED
from orchestrator.infrastructure.chat.slack import MAX_PAGES, SlackChannel

BASE = "https://slack.example.test/api"
TOKEN = "xoxb-1234-5678-sekrit"
AUTH = {"ok": True, "user_id": "UBOT", "user": "orchestrator"}
ROOT = ThreadRef(id="1700000000.000000")


def a_client(handler: Any, **options: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), **options)


def assert_hidden(error: ChatError, *secrets: str) -> None:
    for secret in secrets:
        for text in (error.detail, str(error), repr(error), repr(error.args)):
            assert secret not in text


@pytest.mark.parametrize("token", ["xoxb-sekrit\n", "xoxb sekrit", "xoxb-sëkrit", "\txoxb", ""])
def test_a_token_that_cannot_be_sent_is_refused_without_echoing_it(token: str) -> None:
    with capture_logs() as logs, pytest.raises(ChatError) as caught:
        SlackChannel(BASE, "C1", token, client=a_client(lambda _: httpx.Response(200)))

    assert caught.value.detail == TOKEN_REFUSED
    assert caught.value.__cause__ is None
    if token.strip():
        assert_hidden(caught.value, token, token.strip())
    assert logs == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"ok": False, "error": f"invalid_auth {TOKEN}"}),
        httpx.Response(200, json={"ok": False, "error": "missing_scope", "needed": TOKEN}),
        httpx.Response(500, content=f"upstream said Bearer {TOKEN}".encode()),
        httpx.Response(401, json={"echo": TOKEN}),
    ],
)
def test_a_token_in_any_error_answer_never_reaches_the_detail(response: httpx.Response) -> None:
    channel = SlackChannel(BASE, "C1", TOKEN, client=a_client(lambda _: response))

    with capture_logs() as logs, pytest.raises(ChatError) as caught:
        channel.probe()

    assert "***" in caught.value.detail
    assert_hidden(caught.value, TOKEN)
    assert logs == []


def test_a_token_in_a_transport_error_never_reaches_the_detail() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"refused while sending Bearer {TOKEN}", request=request)

    channel = SlackChannel(BASE, "C1", TOKEN, client=a_client(refuse))

    with pytest.raises(ChatError) as caught:
        channel.post("t", [])

    assert caught.value.detail == "ConnectError: refused while sending Bearer ***"
    assert caught.value.__cause__ is None


def test_a_request_that_cannot_be_built_is_reported_by_class_only() -> None:
    channel = SlackChannel(
        "https://[::1", "C1", TOKEN, client=a_client(lambda _: httpx.Response(200))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "InvalidURL: the request to auth.test could not be built"
    assert_hidden(caught.value, TOKEN)


def test_a_redirect_is_not_followed_even_by_a_client_that_would() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://elsewhere.test/steal"})

    channel = SlackChannel(BASE, "C1", TOKEN, client=a_client(respond, follow_redirects=True))

    with pytest.raises(ChatError, match=r"^auth\.test: 302$"):
        channel.probe()

    assert [r.url.host for r in seen] == ["slack.example.test"]


def test_a_thread_longer_than_the_page_cap_is_refused() -> None:
    reads: list[httpx.Request] = []

    def endless(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return httpx.Response(200, json=AUTH)
        reads.append(request)
        meta = {"next_cursor": f"page:{len(reads)}"}
        return httpx.Response(200, json={"ok": True, "messages": [], "response_metadata": meta})

    channel = SlackChannel(BASE, "C1", TOKEN, client=a_client(endless))

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ROOT, None)

    assert caught.value.detail == f"conversations.replies has more than {MAX_PAGES} pages"
    assert len(reads) == MAX_PAGES


def test_an_answer_larger_than_the_size_cap_is_refused() -> None:
    huge = b"x" * (MAX_RESPONSE_BYTES + 1)
    channel = SlackChannel(
        BASE, "C1", TOKEN, client=a_client(lambda _: httpx.Response(200, content=huge))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == f"auth.test answered more than {MAX_RESPONSE_BYTES} bytes"


def test_the_channel_never_repr_s_its_token() -> None:
    channel = SlackChannel(BASE, "C1", TOKEN, client=a_client(lambda _: httpx.Response(200)))

    assert TOKEN not in repr(channel)


def test_the_default_client_keeps_no_cookies() -> None:
    channel = SlackChannel(BASE, "C1", TOKEN)
    request = httpx.Request("GET", f"{BASE}/auth.test")

    channel._client.cookies.extract_cookies(
        httpx.Response(200, headers={"Set-Cookie": "d=other; Path=/"}, request=request)
    )

    assert list(channel._client.cookies.jar) == []
