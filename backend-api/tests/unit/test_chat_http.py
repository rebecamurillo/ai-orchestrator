"""`infrastructure/chat/http.py`: the transport rules every chat adapter shares (story 3-2).

Moved unchanged out of the Mattermost adapter (3-1) so Slack sends its bearer under the same
rules. The adapters' own suites cover these through each platform; this pins the shared seam.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError
from orchestrator.infrastructure.chat.http import (
    MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS,
    exchange,
    new_client,
    redact_token,
    sendable,
)

URL = "https://chat.example.test/x"


def a_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_the_client_is_bounded_follows_no_redirect_and_keeps_no_cookie() -> None:
    client = new_client()

    assert client.timeout == httpx.Timeout(TIMEOUT_SECONDS)
    assert client.follow_redirects is False
    request = httpx.Request("GET", URL)
    client.cookies.extract_cookies(
        httpx.Response(200, headers={"Set-Cookie": "s=1; Path=/"}, request=request)
    )
    assert list(client.cookies.jar) == []


@pytest.mark.parametrize(
    ("token", "ok"),
    [("xoxb-1", True), ("", False), ("a b", False), ("a\n", False), ("ä", False)],
)
def test_sendable(token: str, ok: bool) -> None:
    assert sendable(token) is ok


def test_redact_token_covers_the_raw_and_escaped_forms() -> None:
    token = "se\\krit"
    text = f"raw {token} repr {repr(token)[1:-1]} bytes {repr(token.encode())[2:-1]}"

    assert redact_token(text, token) == "raw *** repr *** bytes ***"


def test_exchange_sends_the_bearer_and_answers_status_headers_and_body() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, headers={"X-A": "1"}, content=b"{}")

    status, headers, content = exchange(
        a_client(respond),
        "POST",
        URL,
        "tok",
        "x",
        params={"a": "1"},
        json={"k": "v"},
        headers={"Content-Type": "application/json; charset=utf-8"},
    )

    assert (status, headers["X-A"], content) == (201, "1", b"{}")
    assert seen[0].headers["Authorization"] == "Bearer tok"
    assert seen[0].headers["Content-Type"] == "application/json; charset=utf-8"
    assert seen[0].url.params["a"] == "1"


def test_exchange_redacts_a_transport_error_and_drops_its_cause() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route for tok", request=request)

    with pytest.raises(ChatError) as caught:
        exchange(a_client(refuse), "GET", URL, "tok", "x")

    assert caught.value.detail == "ConnectError: no route for ***"
    assert caught.value.__cause__ is None


def test_exchange_names_only_the_class_of_a_request_it_cannot_build() -> None:
    with pytest.raises(ChatError) as caught:
        exchange(a_client(lambda _: httpx.Response(200)), "GET", "https://[::1", "tok", "x")

    assert caught.value.detail == "InvalidURL: the request to x could not be built"


def test_exchange_refuses_an_answer_past_the_cap() -> None:
    huge = b"x" * (MAX_RESPONSE_BYTES + 1)

    with pytest.raises(ChatError) as caught:
        exchange(a_client(lambda _: httpx.Response(200, content=huge)), "GET", URL, "tok", "x")

    assert caught.value.detail == f"x answered more than {MAX_RESPONSE_BYTES} bytes"
