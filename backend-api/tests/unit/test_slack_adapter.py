"""`SlackChannel` over `httpx.MockTransport`: requests, paging, filtering, errors (story 3-2).

The thread endpoint is simulated from the `conversations.replies` reference: the parent first,
then replies earliest first, `limit` at a time, `oldest` exclusive, and the next page named by
`response_metadata.next_cursor`, which is empty on the last page.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatChannel, ChatError, ChatUser, ThreadRef
from orchestrator.infrastructure.chat.slack import PER_PAGE, SlackChannel

BASE = "https://slack.example.test/api"
TOKEN = "xoxb-test-6f1c2e"
CHANNEL = "C0CHAN"
BOT = "UBOT"
AUTH = {"ok": True, "user_id": BOT, "user": "orchestrator", "bot_id": "B1", "team_id": "T1"}
MEMBER = {"ok": True, "channel": {"id": CHANNEL, "is_member": True, "is_archived": False}}
ROOT = ThreadRef(id="1700000000.000000")
ROOT_MESSAGE = {"type": "message", "ts": ROOT.id, "user": BOT, "bot_id": "B1", "text": "q"}
#: A refused probe called twice reads `auth.test` twice: a refusal caches nothing.
TWICE = 2

Handler = Callable[[httpx.Request], httpx.Response]


def refused(detail: str) -> pytest.RaisesExc[ChatError]:
    return pytest.raises(ChatError, match=f"^{re.escape(detail)}$")


def ts(n: int) -> str:
    return f"1700000000.{n:06d}"


def a_message(n: int, **over: Any) -> dict[str, Any]:
    message = {
        "type": "message",
        "ts": ts(n),
        "thread_ts": ROOT.id,
        "user": "U1",
        "text": f"<@{BOT}> answer {n}",
    }
    message.update(over)
    return message


def method(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1]


def thread_server(
    messages: list[dict[str, Any]], *, honour_oldest: bool = True, seen: list[httpx.Request]
) -> Handler:
    replies = sorted(messages, key=lambda m: Decimal(m["ts"]))

    def respond(request: httpx.Request) -> httpx.Response:
        if method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        seen.append(request)
        query = request.url.params
        assert (query["channel"], query["ts"]) == (CHANNEL, ROOT.id)
        later = replies
        if honour_oldest and "oldest" in query:
            later = [m for m in replies if Decimal(m["ts"]) > Decimal(query["oldest"])]
        start = int(query.get("cursor", "page:0").removeprefix("page:"))
        limit = int(query["limit"])
        page = later[start : start + limit]
        more = start + limit < len(later)
        body = {
            "ok": True,
            "messages": [ROOT_MESSAGE, *page],
            "has_more": more,
            "response_metadata": {"next_cursor": f"page:{start + limit}" if more else ""},
        }
        return httpx.Response(200, json=body)

    return respond


def a_channel(handler: Handler, *, token: str = TOKEN) -> SlackChannel:
    return SlackChannel(
        BASE, CHANNEL, token, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def recording(answers: dict[str, dict[str, Any]], seen: list[httpx.Request]) -> Handler:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answers[method(request)])

    return respond


# ── shape ────────────────────────────────────────────────────────────────────


def test_the_adapter_satisfies_the_port_and_has_safe_defaults() -> None:
    channel = SlackChannel(BASE + "/", CHANNEL, TOKEN)

    assert isinstance(channel, ChatChannel)
    assert channel._client.follow_redirects is False
    assert channel._base == BASE


# ── probe ────────────────────────────────────────────────────────────────────


def test_probe_reads_auth_then_the_channel_and_answers_the_bot_user() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"auth.test": AUTH, "conversations.info": MEMBER}, seen))

    assert channel.probe() == "orchestrator"

    assert [(r.method, r.url.path) for r in seen] == [
        ("POST", "/api/auth.test"),
        ("GET", "/api/conversations.info"),
    ]
    assert seen[1].url.params["channel"] == CHANNEL
    assert all(r.headers["Authorization"] == f"Bearer {TOKEN}" for r in seen)
    assert all("token" not in r.url.params and TOKEN not in r.content.decode() for r in seen)


def test_the_bot_id_from_a_probe_is_reused_by_a_thread_read() -> None:
    seen: list[httpx.Request] = []
    handler = thread_server([], seen=seen)
    calls: list[str] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(method(request))
        if method(request) == "conversations.info":
            return httpx.Response(200, json=MEMBER)
        return handler(request)

    channel = a_channel(respond)
    channel.probe()
    channel.replies_since(ROOT, None)
    channel.replies_since(ROOT, None)

    assert calls.count("auth.test") == 1


@pytest.mark.parametrize(
    ("info", "detail"),
    [
        (
            {"ok": True, "channel": {"id": CHANNEL, "is_member": False}},
            f"conversations.info: the bot is not a member of {CHANNEL}",
        ),
        (
            {"ok": True, "channel": {"id": CHANNEL}},
            f"conversations.info: the bot is not a member of {CHANNEL}",
        ),
        (
            {"ok": True, "channel": {"id": CHANNEL, "is_member": True, "is_archived": True}},
            f"conversations.info: {CHANNEL} is archived",
        ),
        ({"ok": False, "error": "channel_not_found"}, "conversations.info: channel_not_found"),
    ],
)
def test_a_bad_channel_is_refused_and_caches_nothing(info: dict[str, Any], detail: str) -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"auth.test": AUTH, "conversations.info": info}, seen))

    for _ in range(TWICE):
        with refused(detail):
            channel.probe()

    assert [method(r) for r in seen].count("auth.test") == TWICE


def test_a_refused_token_is_slacks_own_code() -> None:
    channel = a_channel(lambda _: httpx.Response(200, json={"ok": False, "error": "invalid_auth"}))

    with refused("auth.test: invalid_auth"):
        channel.probe()


# ── post and reply ───────────────────────────────────────────────────────────


def test_post_names_each_user_by_id_on_the_first_line_and_answers_the_ts() -> None:
    seen: list[httpx.Request] = []
    answer = {"ok": True, "channel": CHANNEL, "ts": ts(1), "message": {}}
    channel = a_channel(recording({"chat.postMessage": answer}, seen))

    thread = channel.post("Run blocked", [ChatUser("U1", "ana"), ChatUser("U2", "bo")])

    assert thread == ThreadRef(id=ts(1))
    assert (seen[0].method, seen[0].url.path) == ("POST", "/api/chat.postMessage")
    assert seen[0].headers["Content-Type"] == "application/json; charset=utf-8"
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(seen[0].content) == {"channel": CHANNEL, "text": "<@U1> <@U2>\nRun blocked"}


def test_post_without_mentions_sends_the_text_alone() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"chat.postMessage": {"ok": True, "ts": ts(1)}}, seen))

    channel.post("hello", [])

    assert json.loads(seen[0].content)["text"] == "hello"


def test_outgoing_text_escapes_slacks_control_characters_so_it_pings_nobody() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"chat.postMessage": {"ok": True, "ts": ts(1)}}, seen))

    channel.post("<!channel> a & b <@U9>", [ChatUser("U1", "ana")])
    channel.reply(ROOT, "x > y <!here>")

    texts = [json.loads(r.content)["text"] for r in seen]
    assert texts == [
        "<@U1>\n&lt;!channel&gt; a &amp; b &lt;@U9&gt;",
        "x &gt; y &lt;!here&gt;",
    ]


def test_reply_posts_under_the_root_ts() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"chat.postMessage": {"ok": True, "ts": ts(2)}}, seen))

    channel.reply(ROOT, "on it")

    assert json.loads(seen[0].content) == {
        "channel": CHANNEL,
        "text": "on it",
        "thread_ts": ROOT.id,
    }


@pytest.mark.parametrize("call", ["post", "reply"])
def test_a_refused_post_or_reply_is_slacks_code_with_the_scope_it_needs(call: str) -> None:
    body = {"ok": False, "error": "missing_scope", "needed": "chat:write", "provided": "x"}
    channel = a_channel(lambda _: httpx.Response(200, json=body))

    with refused("chat.postMessage: missing_scope (needed: chat:write)"):
        if call == "post":
            channel.post("t", [])
        else:
            channel.reply(ROOT, "t")


# ── replies ──────────────────────────────────────────────────────────────────


def test_a_first_read_pages_the_whole_thread_oldest_first() -> None:
    seen: list[httpx.Request] = []
    messages = [a_message(n) for n in range(1, 251)]
    channel = a_channel(thread_server(messages[::-1], seen=seen))

    replies = channel.replies_since(ROOT, None)

    assert [r.id for r in replies] == [ts(n) for n in range(1, 251)]
    assert len(seen) == len(("first page", "second page"))
    assert seen[0].url.params["limit"] == str(PER_PAGE)
    assert "cursor" not in seen[0].url.params
    assert "oldest" not in seen[0].url.params
    assert seen[1].url.params["cursor"] == f"page:{PER_PAGE}"
    assert all(r.method == "GET" for r in seen)


def test_a_read_after_a_cursor_sends_oldest_and_returns_only_later_replies() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(thread_server([a_message(n) for n in range(1, 451)], seen=seen))

    replies = channel.replies_since(ROOT, ts(100))

    assert [r.id for r in replies] == [ts(n) for n in range(101, 451)]
    assert len(seen) == len(("first page", "second page"))
    assert {r.url.params["oldest"] for r in seen} == {ts(100)}


def test_replies_at_or_before_the_cursor_are_dropped_when_the_server_ignores_oldest() -> None:
    seen: list[httpx.Request] = []
    messages = [a_message(n) for n in range(1, 6)]
    channel = a_channel(thread_server(messages, honour_oldest=False, seen=seen))

    assert [r.id for r in channel.replies_since(ROOT, ts(3))] == [ts(4), ts(5)]


def test_the_cursor_is_compared_as_a_number_not_as_text() -> None:
    seen: list[httpx.Request] = []
    early, late = a_message(0, ts="999999999.999999"), a_message(0, ts="1700000001.000001")
    channel = a_channel(thread_server([early, late], honour_oldest=False, seen=seen))

    assert [r.id for r in channel.replies_since(ROOT, "1000000000.000000")] == [late["ts"]]


def test_a_reply_carries_its_author_text_body_mention_and_cursor() -> None:
    seen: list[httpx.Request] = []
    text = f"<@{BOT}> fix it <@U7>"
    channel = a_channel(thread_server([a_message(1, user="U9", text=text)], seen=seen))

    (reply,) = channel.replies_since(ROOT, None)

    assert reply.id == reply.cursor == ts(1)
    assert reply.author_id == "U9"
    assert reply.mentions_bot is True
    assert reply.text == text
    assert reply.body == " fix it <@U7>"


def test_a_reply_without_the_bot_mention_is_returned_unmentioned() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(thread_server([a_message(1, text="<@UBOTX> thanks")], seen=seen))

    (reply,) = channel.replies_since(ROOT, None)

    assert (reply.mentions_bot, reply.body) == (False, "<@UBOTX> thanks")


@pytest.mark.parametrize(
    "over",
    [
        {"user": BOT},
        {"subtype": "bot_message"},
        {"subtype": "channel_join"},
        {"subtype": "thread_broadcast"},
        {"subtype": "me_message"},
        {"bot_id": "B9"},
        {"bot_profile": {"id": "B9"}},
        {"app_id": "A9"},
        {"bot_id": False},
        {"type": "file"},
        {"user": None},
        {"user": ""},
        {"text": None},
    ],
)
def test_a_message_that_is_not_a_persons_reply_is_dropped(over: dict[str, Any]) -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(thread_server([a_message(1, **over), a_message(2)], seen=seen))

    assert [r.id for r in channel.replies_since(ROOT, None)] == [ts(2)]


def test_the_root_is_never_a_reply_even_when_a_person_wrote_it() -> None:
    seen: list[httpx.Request] = []
    root = {"type": "message", "ts": ROOT.id, "user": "U1", "text": f"<@{BOT}> hi"}

    def respond(request: httpx.Request) -> httpx.Response:
        if method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "messages": [root]})

    assert a_channel(respond).replies_since(ROOT, None) == []
    assert len(seen) == 1


@pytest.mark.parametrize("cursor", ["", "abc", "1700000000", "1700000000.", ".5", "1.2.3", " 1.2"])
def test_a_malformed_cursor_is_refused_before_any_request(cursor: str) -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({}, seen))

    with refused(f"malformed cursor {cursor!r}"):
        channel.replies_since(ROOT, cursor)

    assert seen == []


def test_a_next_cursor_that_repeats_is_an_unexpected_response() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        body = {"ok": True, "messages": [], "response_metadata": {"next_cursor": "same"}}
        return httpx.Response(200, json=body)

    with refused("unexpected response from conversations.replies"):
        a_channel(respond).replies_since(ROOT, None)


def test_a_refused_thread_read_is_slacks_code() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        return httpx.Response(200, json={"ok": False, "error": "thread_not_found"})

    with refused("conversations.replies: thread_not_found"):
        a_channel(respond).replies_since(ROOT, None)


# ── errors ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("headers", "detail"),
    [
        ({"Retry-After": "30"}, "conversations.replies: 429 rate limited, Retry-After 30 s"),
        ({}, "conversations.replies: 429 rate limited, no Retry-After given"),
        ({"Retry-After": "soon"}, "conversations.replies: 429 rate limited, no Retry-After given"),
    ],
)
def test_a_429_names_retry_after_and_is_not_retried(headers: dict[str, str], detail: str) -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        if method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        seen.append(request)
        return httpx.Response(429, headers=headers, json={"ok": False, "error": "ratelimited"})

    with refused(detail):
        a_channel(respond).replies_since(ROOT, None)

    assert len(seen) == 1


@pytest.mark.parametrize(
    "answer",
    [
        {"ok": False},
        {"ok": False, "error": 7},
        {"ok": "true", "ts": ts(1)},
        {"error": "x"},
    ],
)
def test_an_answer_that_is_not_ok_true_is_refused(answer: dict[str, Any]) -> None:
    channel = a_channel(lambda _: httpx.Response(200, json=answer))

    with pytest.raises(ChatError, match=r"^chat\.postMessage: "):
        channel.post("t", [])


@pytest.mark.parametrize(
    ("call", "body"),
    [
        ("post", "<html>ok</html>"),
        ("post", "[]"),
        ("post", '{"ok": true}'),
        ("post", '{"ok": true, "ts": 17}'),
        ("post", '{"ok": true, "ts": "not-a-ts"}'),
        ("probe", '{"ok": true, "user": "b"}'),
        ("probe", '{"ok": true, "user_id": "U", "user": 3}'),
        ("read", '{"ok": true, "messages": {}}'),
        ("read", '{"ok": true, "messages": ["x"]}'),
        ("read", '{"ok": true, "messages": [{"ts": 1}]}'),
        ("read", '{"ok": true, "messages": [{"ts": "1.x"}]}'),
        ("read", '{"ok": true, "messages": [], "response_metadata": []}'),
        ("read", '{"ok": true, "messages": [], "response_metadata": {"next_cursor": 5}}'),
    ],
)
def test_an_answer_that_is_not_the_expected_json_is_a_chat_error(call: str, body: str) -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if call == "read" and method(request) == "auth.test":
            return httpx.Response(200, json=AUTH)
        return httpx.Response(200, content=body.encode())

    channel = a_channel(respond)
    name = {"post": "chat.postMessage", "probe": "auth.test", "read": "conversations.replies"}

    with refused(f"unexpected response from {name[call]}"):
        if call == "post":
            channel.post("t", [])
        elif call == "probe":
            channel.probe()
        else:
            channel.replies_since(ROOT, None)


def test_a_probe_whose_channel_answer_has_no_channel_object_is_unexpected() -> None:
    seen: list[httpx.Request] = []
    channel = a_channel(recording({"auth.test": AUTH, "conversations.info": {"ok": True}}, seen))

    with refused("unexpected response from conversations.info"):
        channel.probe()


def test_a_server_error_names_its_status_and_a_cut_body() -> None:
    channel = a_channel(lambda _: httpx.Response(503, content=b"x" * 1000))

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "auth.test: 503 " + "x" * 300


def test_a_server_error_with_no_body_names_its_status_alone() -> None:
    with refused("auth.test: 500"):
        a_channel(lambda _: httpx.Response(500)).probe()
