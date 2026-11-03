"""How each adapter tells a deleted thread and a rate limit apart from other failures, and
orders its own cursors (story 4-3, AD-25): `ChatThreadGone` and `ChatRateLimited` are
`ChatError`s the read pass catches by class, so no application code parses a detail."""

from __future__ import annotations

import httpx
import pytest

from orchestrator.domain.ports.chat import ChatError, ChatRateLimited, ChatThreadGone, ThreadRef
from orchestrator.infrastructure.chat.mattermost import MattermostChannel
from orchestrator.infrastructure.chat.slack import SlackChannel

MM_BASE = "https://chat.example.test"
MM_TOKEN = "mm-token-6f1c2e"
MM_ME = {"id": "bot-id", "username": "bot"}
SLACK_BASE = "https://slack.example.test/api"
SLACK_TOKEN = "xoxb-test-6f1c2e"
SLACK_AUTH = {"ok": True, "user_id": "UBOT", "user": "orchestrator", "bot_id": "B1"}
ROOT = ThreadRef(id="root")
SLACK_ROOT = ThreadRef(id="1700000000.000000")


def mattermost(thread: httpx.Response, me: httpx.Response | None = None) -> MattermostChannel:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v4/users/me":
            return me or httpx.Response(200, json=MM_ME)
        return thread

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return MattermostChannel(MM_BASE, "ch1", MM_TOKEN, client=client)


def slack(replies: httpx.Response, auth: httpx.Response | None = None) -> SlackChannel:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth.test"):
            return auth or httpx.Response(200, json=SLACK_AUTH)
        return replies

    client = httpx.Client(transport=httpx.MockTransport(respond))
    return SlackChannel(SLACK_BASE, "C0CHAN", SLACK_TOKEN, client=client)


def app_error(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"id": "api.x", "message": message, "status_code": status})


# ── Mattermost ──────────────────────────────────────────────────────────────────────────


def test_mattermost_a_thread_whose_root_is_gone_is_thread_gone_redacted() -> None:
    channel = mattermost(app_error(404, f"Unable to find the post {MM_TOKEN}"))

    with pytest.raises(ChatThreadGone) as caught:
        channel.replies_since(ROOT, None)

    assert caught.value.detail == "404 Unable to find the post ***"


def test_mattermost_a_404_outside_the_thread_read_is_a_plain_chat_error() -> None:
    channel = mattermost(httpx.Response(200), me=app_error(404, "no such user"))

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ROOT, None)

    assert not isinstance(caught.value, ChatThreadGone | ChatRateLimited)
    assert caught.value.detail == "404 no such user"


def test_mattermost_a_429_is_a_rate_limit() -> None:
    channel = mattermost(app_error(429, "command with too many requests"))

    with pytest.raises(ChatRateLimited) as caught:
        channel.replies_since(ROOT, None)

    assert caught.value.detail == "429 command with too many requests"


def test_mattermost_any_other_failure_is_a_plain_chat_error() -> None:
    channel = mattermost(app_error(500, "boom"))

    with pytest.raises(ChatError) as caught:
        channel.replies_since(ROOT, None)

    assert type(caught.value) is ChatError


@pytest.mark.parametrize(
    ("cursor", "after", "follows"),
    [
        ("2001:p001", None, True),
        ("2002:p001", "2001:p009", True),
        ("2001:p002", "2001:p001", True),
        ("2001:p001", "2001:p001", False),
        ("2001:p001", "2002:p000", False),
    ],
)
def test_mattermost_orders_its_cursors_by_time_then_id(
    cursor: str, after: str | None, follows: bool
) -> None:
    assert mattermost(httpx.Response(200)).follows(cursor, after) is follows


def test_mattermost_a_malformed_cursor_cannot_be_ordered() -> None:
    with pytest.raises(ChatError):
        mattermost(httpx.Response(200)).follows("p001", None)


# ── Slack ───────────────────────────────────────────────────────────────────────────────


def test_slack_thread_not_found_on_a_read_is_thread_gone() -> None:
    channel = slack(httpx.Response(200, json={"ok": False, "error": "thread_not_found"}))

    with pytest.raises(ChatThreadGone) as caught:
        channel.replies_since(SLACK_ROOT, None)

    assert caught.value.detail == "conversations.replies: thread_not_found"


def test_slack_thread_not_found_elsewhere_is_a_plain_chat_error() -> None:
    refused = httpx.Response(200, json={"ok": False, "error": "thread_not_found"})
    channel = slack(httpx.Response(200), auth=refused)

    with pytest.raises(ChatError) as caught:
        channel.replies_since(SLACK_ROOT, None)

    assert type(caught.value) is ChatError


def test_slack_an_http_429_is_a_rate_limit() -> None:
    channel = slack(httpx.Response(429, headers={"Retry-After": "30"}))

    with pytest.raises(ChatRateLimited) as caught:
        channel.replies_since(SLACK_ROOT, None)

    assert caught.value.detail == "conversations.replies: 429 rate limited, Retry-After 30 s"


def test_slack_a_ratelimited_refusal_is_a_rate_limit() -> None:
    channel = slack(httpx.Response(200, json={"ok": False, "error": "ratelimited"}))

    with pytest.raises(ChatRateLimited) as caught:
        channel.replies_since(SLACK_ROOT, None)

    assert caught.value.detail == "conversations.replies: ratelimited"


def test_slack_any_other_refusal_is_a_plain_chat_error() -> None:
    channel = slack(httpx.Response(200, json={"ok": False, "error": "channel_not_found"}))

    with pytest.raises(ChatError) as caught:
        channel.replies_since(SLACK_ROOT, None)

    assert type(caught.value) is ChatError


@pytest.mark.parametrize(
    ("cursor", "after", "follows"),
    [
        ("1700000000.000002", None, True),
        ("1700000000.000010", "1700000000.000009", True),
        ("1700000001.000000", "1700000000.999999", True),
        ("1700000000.000001", "1700000000.000001", False),
        ("1700000000.000001", "1700000000.000002", False),
    ],
)
def test_slack_orders_its_cursors_as_timestamps(
    cursor: str, after: str | None, follows: bool
) -> None:
    assert slack(httpx.Response(200)).follows(cursor, after) is follows


def test_slack_a_malformed_cursor_cannot_be_ordered() -> None:
    with pytest.raises(ChatError):
        slack(httpx.Response(200)).follows("1700000000.000001", "yesterday")
