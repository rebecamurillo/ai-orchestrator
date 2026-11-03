"""`MattermostChannel` over `httpx.MockTransport`: requests, paging, filtering, errors (story 3-1).

The thread endpoint is simulated with the store's paging rule (`sqlstore/post_store.go::Get`):
posts after `(fromCreateAt, fromPost)`, ordered `CreateAt, Id` ascending, `perPage` at a time.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatChannel, ChatError, ChatUser, ThreadRef
from orchestrator.infrastructure.chat.mattermost import (
    ERROR_BODY_LIMIT,
    PER_PAGE,
    TIMEOUT_SECONDS,
    MattermostChannel,
)

BASE = "https://chat.example.test"
TOKEN = "mm-token-6f1c2e"
CHANNEL = "ch1"
ME = {"id": "bot-id", "username": "bot"}
ROOT = ThreadRef(id="root")
ROOT_POST = {"id": "root", "create_at": 1000, "user_id": "bot-id", "root_id": "", "message": "hi"}

#: A probe refused twice reads `/users/me` twice: a refusal caches nothing.
TWICE = 2

Handler = Callable[[httpx.Request], httpx.Response]


def refused(detail: str) -> pytest.RaisesExc[ChatError]:
    return pytest.raises(ChatError, match=f"^{re.escape(detail)}$")


def app_error(status: int, message: str) -> httpx.Response:
    body = {"id": "api.x.app_error", "message": message, "request_id": "rq", "status_code": status}
    return httpx.Response(status, json=body)


def a_post(n: int, **over: Any) -> dict[str, Any]:
    post = {
        "id": f"p{n:03d}",
        "create_at": 2000 + n,
        "user_id": "u1",
        "root_id": "root",
        "message": f"@bot answer {n}",
        "type": "",
        "props": {},
    }
    post.update(over)
    return post


def thread_server(posts: list[dict[str, Any]], *, reverse: bool = False) -> Handler:
    every = sorted([ROOT_POST, *posts], key=lambda p: (p["create_at"], p["id"]))

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/users/me":
            return httpx.Response(200, json=ME)
        query = request.url.params
        assert query["direction"] == "down"
        after = (int(query.get("fromCreateAt", "-1")), query.get("fromPost", ""))
        later = [p for p in every if (p["create_at"], p["id"]) > after]
        page = later[: int(query["perPage"])]
        order = [p["id"] for p in page]
        body = {
            "order": order[::-1] if reverse else order,
            "posts": {p["id"]: p for p in page},
            "has_next": len(later) > len(page),
        }
        return httpx.Response(200, json=body)

    return respond


def a_channel(handler: Handler, **client: Any) -> tuple[MattermostChannel, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def record(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    http = httpx.Client(transport=httpx.MockTransport(record), **client)
    return MattermostChannel(f"{BASE}/", CHANNEL, TOKEN, client=http), requests


def routes(table: dict[str, httpx.Response]) -> Handler:
    return lambda request: table[request.url.path]


def thread_reads(requests: list[httpx.Request]) -> list[httpx.Request]:
    return [r for r in requests if r.url.path == "/api/v4/posts/root/thread"]


def test_the_adapter_satisfies_the_port_and_has_safe_defaults() -> None:
    channel = MattermostChannel(BASE, CHANNEL, TOKEN)

    assert isinstance(channel, ChatChannel)
    assert channel._client.timeout == httpx.Timeout(TIMEOUT_SECONDS)
    assert channel._client.follow_redirects is False


def test_probe_reads_me_then_the_membership_and_answers_the_username() -> None:
    channel, requests = a_channel(
        routes(
            {
                "/api/v4/users/me": httpx.Response(200, json=ME),
                "/api/v4/channels/ch1/members/bot-id": httpx.Response(200, json={}),
            }
        )
    )

    assert channel.probe() == "bot"
    assert [(r.method, str(r.url)) for r in requests] == [
        ("GET", f"{BASE}/api/v4/users/me"),
        ("GET", f"{BASE}/api/v4/channels/ch1/members/bot-id"),
    ]
    assert {r.headers["Authorization"] for r in requests} == {f"Bearer {TOKEN}"}


def test_a_refused_token_caches_nothing() -> None:
    channel, requests = a_channel(
        routes({"/api/v4/users/me": app_error(401, "Invalid or expired session.")})
    )

    for _ in range(2):
        with pytest.raises(ChatError) as caught:
            channel.probe()
        assert caught.value.detail == "401 Invalid or expired session."

    assert len(requests) == TWICE


@pytest.mark.parametrize("status", [403, 404])
def test_a_bot_outside_the_channel_is_refused_and_caches_nothing(status: int) -> None:
    channel, requests = a_channel(
        routes(
            {
                "/api/v4/users/me": httpx.Response(200, json=ME),
                "/api/v4/channels/ch1/members/bot-id": app_error(status, "Not in channel."),
            }
        )
    )

    with refused(f"{status} Not in channel."):
        channel.probe()
    with pytest.raises(ChatError):
        channel.probe()

    assert [r.url.path for r in requests].count("/api/v4/users/me") == TWICE


def test_post_names_each_user_on_its_own_first_line() -> None:
    channel, requests = a_channel(lambda _: httpx.Response(201, json={"id": "post-1"}))
    users = [ChatUser(id="u1", handle="a"), ChatUser(id="u2", handle="b")]

    thread = channel.post("Run needs you", users)

    assert thread == ThreadRef(id="post-1")
    [request] = requests
    assert (request.method, str(request.url)) == ("POST", f"{BASE}/api/v4/posts")
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == {"channel_id": CHANNEL, "message": "@a @b\nRun needs you"}


def test_post_without_mentions_sends_the_text_alone() -> None:
    channel, requests = a_channel(lambda _: httpx.Response(201, json={"id": "post-1"}))

    channel.post("Run needs you", [])

    assert json.loads(requests[0].content)["message"] == "Run needs you"


def test_reply_posts_under_the_root() -> None:
    channel, requests = a_channel(lambda _: httpx.Response(201, json={"id": "post-2"}))

    assert channel.reply(ROOT, "Answer received.") is None
    assert json.loads(requests[0].content) == {
        "channel_id": CHANNEL,
        "message": "Answer received.",
        "root_id": "root",
    }


@pytest.mark.parametrize("call", ["post", "reply"])
def test_a_refused_post_or_reply_is_a_chat_error(call: str) -> None:
    channel, _ = a_channel(lambda _: app_error(403, "You do not have the appropriate permissions."))

    with refused("403 You do not have the appropriate permissions."):
        if call == "post":
            channel.post("text", [])
        else:
            channel.reply(ROOT, "text")


def test_a_first_read_pages_the_whole_thread_oldest_first() -> None:
    mine = a_post(5, id="mine", user_id="bot-id")
    channel, requests = a_channel(thread_server([a_post(n) for n in range(1, 251)] + [mine]))

    replies = channel.replies_since(ROOT, None)

    assert [r.id for r in replies] == [f"p{n:03d}" for n in range(1, 251)]
    first, second = thread_reads(requests)
    assert dict(first.url.params) == {"perPage": str(PER_PAGE), "direction": "down"}
    assert dict(second.url.params) == {
        "perPage": str(PER_PAGE),
        "direction": "down",
        "fromCreateAt": "2198",
        "fromPost": "p198",
    }


def test_a_read_after_reply_100_of_250_returns_101_to_250_from_the_cursor() -> None:
    channel, requests = a_channel(thread_server([a_post(n) for n in range(1, 251)]))

    replies = channel.replies_since(ROOT, "2100:p100")

    assert [r.id for r in replies] == [f"p{n:03d}" for n in range(101, 251)]
    [read] = thread_reads(requests)
    assert (read.url.params["fromCreateAt"], read.url.params["fromPost"]) == ("2100", "p100")


def test_a_read_after_a_cursor_pages_until_the_thread_ends() -> None:
    channel, requests = a_channel(thread_server([a_post(n) for n in range(1, 451)]))

    replies = channel.replies_since(ROOT, "2100:p100")

    assert [r.id for r in replies] == [f"p{n:03d}" for n in range(101, 451)]
    first, second = thread_reads(requests)
    assert (first.url.params["fromCreateAt"], first.url.params["fromPost"]) == ("2100", "p100")
    assert (second.url.params["fromCreateAt"], second.url.params["fromPost"]) == ("2300", "p300")


def test_a_page_in_any_order_is_returned_oldest_first() -> None:
    channel, _ = a_channel(thread_server([a_post(n) for n in range(1, 4)], reverse=True))

    assert [r.id for r in channel.replies_since(ROOT, None)] == ["p001", "p002", "p003"]


def test_a_reply_carries_its_author_text_body_mention_and_cursor() -> None:
    post = a_post(1, message="@bot fix @botty and @Bot.", create_at=1700, id="abc")
    channel, _ = a_channel(thread_server([post, a_post(2, message="no mention")]))

    first, second = channel.replies_since(ROOT, None)

    assert (first.id, first.author_id, first.mentions_bot) == ("abc", "u1", True)
    assert first.text == "@bot fix @botty and @Bot."
    assert first.body == " fix @botty and ."
    assert first.cursor == "1700:abc"
    assert (second.mentions_bot, second.body) == (False, "no mention")


def test_posts_that_are_not_a_person_are_dropped() -> None:
    posts = [
        a_post(1, type="system_join_channel"),
        a_post(2, props={"from_webhook": "true"}),
        a_post(3, props={"from_bot": "true"}),
        a_post(4, props={"from_plugin": "true"}),
        a_post(5, props={"from_webhook": "false"}),
        a_post(6),
    ]
    del posts[5]["type"], posts[5]["props"]
    channel, _ = a_channel(thread_server(posts))

    assert [r.id for r in channel.replies_since(ROOT, None)] == ["p005", "p006"]


def test_posts_at_or_before_the_cursor_are_dropped_even_if_the_server_sends_them() -> None:
    page = {"order": ["p001", "p002"], "posts": {"p001": a_post(1), "p002": a_post(2)}}
    channel, _ = a_channel(
        lambda r: httpx.Response(200, json=ME if r.url.path.endswith("/me") else page)
    )

    assert [r.id for r in channel.replies_since(ROOT, "2001:p001")] == ["p002"]


def test_me_is_read_once_per_channel() -> None:
    channel, requests = a_channel(thread_server([a_post(1)]))

    channel.replies_since(ROOT, None)
    channel.replies_since(ROOT, "2001:p001")

    assert [r.url.path for r in requests].count("/api/v4/users/me") == 1


@pytest.mark.parametrize("cursor", ["", "abc", "x:abc", "1700:", ":abc", "-5:abc"])
def test_a_malformed_cursor_is_refused_before_any_request(cursor: str) -> None:
    channel, requests = a_channel(thread_server([]))

    with pytest.raises(ChatError, match="malformed cursor"):
        channel.replies_since(ROOT, cursor)

    assert requests == []


def test_a_page_that_does_not_advance_is_an_unexpected_response() -> None:
    page = {"order": ["p001"], "posts": {"p001": a_post(1)}, "has_next": True}
    channel, _ = a_channel(
        lambda r: httpx.Response(200, json=ME if r.url.path.endswith("/me") else page)
    )

    with refused("unexpected response from /api/v4/posts/root/thread"):
        channel.replies_since(ROOT, None)


def test_an_empty_page_ends_the_read() -> None:
    page = {"order": [], "posts": {}, "has_next": True}
    channel, requests = a_channel(
        lambda r: httpx.Response(200, json=ME if r.url.path.endswith("/me") else page)
    )

    assert channel.replies_since(ROOT, None) == []
    assert len(thread_reads(requests)) == 1


def test_an_unreachable_host_is_a_chat_error_naming_the_failure() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    channel, _ = a_channel(refuse)

    with pytest.raises(ChatError) as caught:
        channel.post("text", [])

    assert caught.value.detail == "ConnectError: connection refused"


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v4/users/me", "<html>login</html>"),
        ("/api/v4/users/me", json.dumps({"id": "bot-id"})),
        ("/api/v4/users/me", json.dumps(["bot"])),
        ("/api/v4/posts/root/thread", json.dumps({"posts": {}})),
        ("/api/v4/posts/root/thread", json.dumps({"order": ["p1"], "posts": {}})),
        ("/api/v4/posts/root/thread", json.dumps({"order": "p1", "posts": {}})),
        (
            "/api/v4/posts/root/thread",
            json.dumps({"order": ["p1"], "posts": {"p1": {**a_post(1), "create_at": "x"}}}),
        ),
        (
            "/api/v4/posts/root/thread",
            json.dumps({"order": ["p1"], "posts": {"p1": {**a_post(1), "props": []}}}),
        ),
    ],
)
def test_an_answer_that_is_not_the_expected_json_is_a_chat_error(path: str, body: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == path:
            return httpx.Response(200, text=body)
        return httpx.Response(200, json=ME)

    channel, _ = a_channel(respond)

    with refused(f"unexpected response from {path}"):
        channel.replies_since(ROOT, None)


@pytest.mark.parametrize("body", [{"message": "x"}, {"id": 7}, "<html/>"])
def test_a_post_answer_without_an_id_is_a_chat_error(body: object) -> None:
    channel, _ = a_channel(
        lambda _: (
            httpx.Response(201, json=body)
            if isinstance(body, dict)
            else httpx.Response(201, text=str(body))
        )
    )

    with refused("unexpected response from /api/v4/posts"):
        channel.post("text", [])
    with refused("unexpected response from /api/v4/posts"):
        channel.reply(ROOT, "text")


def test_an_error_body_that_is_not_an_app_error_is_cut() -> None:
    channel, _ = a_channel(lambda _: httpx.Response(502, text="x" * 1000))

    with pytest.raises(ChatError) as caught:
        channel.post("text", [])

    assert caught.value.detail == "502 " + "x" * ERROR_BODY_LIMIT


@pytest.mark.parametrize(
    "response",
    [
        app_error(401, f"token {TOKEN} is invalid"),
        httpx.Response(500, text=f"upstream said Bearer {TOKEN}"),
    ],
)
def test_a_token_in_the_error_body_never_reaches_the_detail(response: httpx.Response) -> None:
    channel, _ = a_channel(lambda _: response)

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert TOKEN not in caught.value.detail
    assert TOKEN not in str(caught.value)
    assert "***" in caught.value.detail


def test_a_token_in_a_transport_error_never_reaches_the_detail() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"timed out holding {TOKEN}", request=request)

    channel, _ = a_channel(refuse)

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ROOT, None)

    assert caught.value.detail == "ReadTimeout: timed out holding ***"


def test_a_redirect_is_not_followed_even_by_a_client_that_would() -> None:
    elsewhere = "https://elsewhere.example.test/api/v4/users/me"
    channel, requests = a_channel(
        lambda _: httpx.Response(302, headers={"Location": elsewhere}), follow_redirects=True
    )

    with pytest.raises(ChatError, match=r"^302\b"):
        channel.probe()

    assert [r.url.host for r in requests] == ["chat.example.test"]
