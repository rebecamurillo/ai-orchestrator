"""Chat adapter hardening from the story 3-2 review (2026-11-02).

D1: an error excerpt is redacted before it is cut, so a token straddling the cut cannot leak
its prefix. D2: Slack's `>>>` quotes the rest of the message. D3: a mention that cannot be
rendered safely is refused without echoing it. D4: a Slack bot token travels only over https.
Also: Slack posts unfurl nothing, and `auth.test` must name a bot.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError, ChatUser, ThreadRef
from orchestrator.infrastructure.chat.http import ERROR_BODY_LIMIT, excerpt
from orchestrator.infrastructure.chat.mattermost import MattermostChannel
from orchestrator.infrastructure.chat.mentions import slack_mentions_bot, slack_strip_mentions
from orchestrator.infrastructure.chat.slack import SlackChannel

TOKEN = "xoxb-11111-22222-abcdefabcdef"
PREFIX = TOKEN[:10]
#: Where a token starts so that a 300-character cut splits it.
STRADDLE = ERROR_BODY_LIMIT - 10
SLACK = "https://slack.example.test/api"
MATTERMOST = "https://chat.example.test"
AUTH = {"ok": True, "user_id": "UBOT", "user": "orchestrator", "bot_id": "B1"}


def a_client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def straddling() -> str:
    return "x" * STRADDLE + TOKEN + " tail"


def assert_no_token(error: ChatError) -> None:
    for text in (error.detail, str(error), repr(error)):
        assert PREFIX not in text
        assert TOKEN not in text


# ── D1: redact, then cut ─────────────────────────────────────────────────────


def test_excerpt_redacts_before_it_cuts() -> None:
    cut = excerpt(straddling(), TOKEN)

    assert cut == ("x" * STRADDLE + "*** tail")[:ERROR_BODY_LIMIT]
    assert PREFIX not in cut
    assert len(excerpt("y" * 1000, TOKEN)) == ERROR_BODY_LIMIT


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(503, content=straddling().encode()),
        httpx.Response(200, json={"ok": False, "error": straddling()}),
        httpx.Response(200, json={"ok": False, "error": "missing_scope", "needed": straddling()}),
    ],
)
def test_a_slack_error_never_leaks_a_straddling_token_prefix(response: httpx.Response) -> None:
    channel = SlackChannel(SLACK, "C1", TOKEN, client=a_client(lambda _: response))

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert_no_token(caught.value)
    assert "***" in caught.value.detail


def test_a_slack_error_code_is_capped() -> None:
    answer = {"ok": False, "error": "e" * 1000}
    channel = SlackChannel(
        SLACK, "C1", TOKEN, client=a_client(lambda _: httpx.Response(200, json=answer))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "auth.test: " + "e" * ERROR_BODY_LIMIT


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(502, content=straddling().encode()),
        httpx.Response(401, json={"id": "api.x", "message": straddling(), "status_code": 401}),
    ],
)
def test_a_mattermost_error_never_leaks_a_straddling_token_prefix(
    response: httpx.Response,
) -> None:
    channel = MattermostChannel(MATTERMOST, "ch1", TOKEN, client=a_client(lambda _: response))

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert_no_token(caught.value)
    assert "***" in caught.value.detail


def test_a_mattermost_app_error_message_is_capped() -> None:
    body = {"id": "api.x", "message": "m" * 1000, "status_code": 400}
    channel = MattermostChannel(
        MATTERMOST, "ch1", TOKEN, client=a_client(lambda _: httpx.Response(400, json=body))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "400 " + "m" * ERROR_BODY_LIMIT


# ── D2: Slack's block quote ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("&gt;&gt;&gt; quoted\n<@UBOT> do it", False),
        (">>> quoted\n<@UBOT> do it", False),
        ("  &gt;&gt;&gt; quoted\n\n<@UBOT>", False),
        ("&gt;&gt;&gt;<@UBOT>", False),
        ("<@UBOT> asked first\n&gt;&gt;&gt; then quoted <@UBOT>", True),
        ("not a quote &gt;&gt;&gt; mid-line\n<@UBOT>", True),
    ],
)
def test_a_block_quote_masks_every_line_after_it(text: str, expected: bool) -> None:
    assert slack_mentions_bot(text, "UBOT") is expected


def test_strip_keeps_a_mention_inside_a_block_quote() -> None:
    text = "<@UBOT> go\n&gt;&gt;&gt; <@UBOT> old"

    assert slack_strip_mentions(text, "UBOT") == " go\n&gt;&gt;&gt; <@UBOT> old"


# ── D3: mentions rendered only when safe ─────────────────────────────────────


def recorder(seen: list[httpx.Request], answer: dict[str, Any]) -> httpx.Client:
    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=answer)

    return a_client(respond)


@pytest.mark.parametrize("user_id", ["U1><!channel", "u1", "U1 ", "", "U1|x", "<!here>"])
def test_slack_refuses_a_mention_id_it_cannot_render_safely(user_id: str) -> None:
    seen: list[httpx.Request] = []
    channel = SlackChannel(SLACK, "C1", TOKEN, client=recorder(seen, {"ok": True, "ts": "1.2"}))

    with pytest.raises(ChatError) as caught:
        channel.post("hi", [ChatUser("U2", "bo"), ChatUser(user_id, "x")])

    assert caught.value.detail == "a mention's user id is not a Slack user id"
    assert seen == []


@pytest.mark.parametrize("handle", ["ana\n@channel", "Ana", "a b", "", "ana@x", "ana,@all"])
def test_mattermost_refuses_a_mention_handle_it_cannot_render_safely(handle: str) -> None:
    seen: list[httpx.Request] = []
    channel = MattermostChannel(MATTERMOST, "ch1", TOKEN, client=recorder(seen, {"id": "p"}))

    with pytest.raises(ChatError) as caught:
        channel.post("hi", [ChatUser("u2", "bo"), ChatUser("u1", handle)])

    assert caught.value.detail == "a mention's handle is not a Mattermost username"
    assert seen == []


def test_mattermost_renders_a_username_with_dots_dashes_and_underscores() -> None:
    seen: list[httpx.Request] = []
    channel = MattermostChannel(MATTERMOST, "ch1", TOKEN, client=recorder(seen, {"id": "p"}))

    channel.post("hi", [ChatUser("u1", "ana.b-c_d9")])

    assert json.loads(seen[0].content)["message"] == "@ana.b-c_d9\nhi"


# ── D4: https only for Slack ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    "base_url", ["http://slack.com/api", "ftp://slack.com/api", "slack.com/api"]
)
def test_a_slack_base_url_that_is_not_https_is_refused(base_url: str) -> None:
    with pytest.raises(ChatError) as caught:
        SlackChannel(base_url, "C1", TOKEN, client=a_client(lambda _: httpx.Response(200)))

    assert caught.value.detail == "a Slack base URL must use https"
    assert TOKEN not in repr(caught.value)


def test_a_mattermost_lan_host_may_use_http() -> None:
    seen: list[httpx.Request] = []
    channel = MattermostChannel(
        "http://10.0.0.5:8065", "ch1", TOKEN, client=recorder(seen, {"id": "p"})
    )

    channel.post("hi", [])

    assert seen[0].url.scheme == "http"


# ── nits ─────────────────────────────────────────────────────────────────────


def test_slack_posts_and_replies_unfurl_nothing() -> None:
    seen: list[httpx.Request] = []
    channel = SlackChannel(SLACK, "C1", TOKEN, client=recorder(seen, {"ok": True, "ts": "1.2"}))

    channel.post("see https://example.test", [])
    channel.reply(ThreadRef(id="1.2"), "and https://example.test")

    for request in seen:
        body = json.loads(request.content)
        assert (body["unfurl_links"], body["unfurl_media"]) == (False, False)


@pytest.mark.parametrize(
    "auth",
    [
        {k: v for k, v in AUTH.items() if k != "bot_id"},
        {**AUTH, "bot_id": ""},
        {**AUTH, "bot_id": 7},
    ],
)
def test_a_token_that_is_not_a_bot_token_is_refused(auth: dict[str, Any]) -> None:
    channel = SlackChannel(
        SLACK, "C1", TOKEN, client=a_client(lambda _: httpx.Response(200, json=auth))
    )

    with pytest.raises(ChatError) as caught:
        channel.probe()

    assert caught.value.detail == "auth.test: the token is not a bot token"
