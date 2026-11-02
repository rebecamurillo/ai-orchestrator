"""`SlackChannel`: the `ChatChannel` port over Slack's Web API (AD-25, story 3-2).

`base_url` is the Web API root (`https://slack.com/api`) and each call is
`{base_url}/{method}`. The transport rules (bearer only to that host, no redirects, no
cookies, capped answers, no retry, no logging) are `http.py`'s, shared with Mattermost. Slack
answers a refused call with HTTP 200 and `{"ok": false, "error": "<code>"}`. That code, after
the method name, is the `ChatError` detail. A 429 names its `Retry-After` and is not waited out.

The bot must be an internal app installed in the team's own workspace. Since 2025-05-29 a
commercially distributed app outside the Marketplace gets one `conversations.replies` call a
minute and 15 messages a page, which no thread poll survives.

Outgoing text has `&`, `<` and `>` escaped, so text an agent wrote cannot ping `<!channel>`.
A reply's `text` and `body` are plain text: those three entities are decoded after the bot
mention is matched on the raw markup, and other people's `<@U…>` stay as written.
A thread is read past `oldest`, and every message at or before the cursor is dropped again
here, so a server that ignores `oldest` cannot hand a reply over twice.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import httpx

from orchestrator.domain.ports.chat import ChatError, ChatUser, Reply, ThreadRef
from orchestrator.infrastructure.chat.http import (
    TOKEN_REFUSED,
    Params,
    exchange,
    new_client,
    redact_token,
    sendable,
)
from orchestrator.infrastructure.chat.mentions import slack_mentions_bot, slack_strip_mentions

#: Under the page size `conversations.replies` recommends.
PER_PAGE = 200
#: Bounds on one thread read, since `next_cursor` is the server's to choose.
MAX_PAGES = 50
#: How much of a non-2xx body a detail carries.
ERROR_BODY_LIMIT = 300
#: Any of these, set to anything, marks a message that is not a person's own words: a bot,
#: an app or workflow posting under someone's id, or an event (join, broadcast, edit).
NOT_A_PERSON = ("subtype", "bot_id", "bot_profile", "app_id")
JSON_UTF8 = {"Content-Type": "application/json; charset=utf-8"}
_TS = re.compile(r"[0-9]+\.[0-9]+")
_ESCAPES = (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"))
_RETRY_AFTER = re.compile(r"[0-9]+")
_TOO_MANY = 429

Page = tuple[list[dict[str, Any]], str]


class _Unexpected(Exception):
    """An answer that is not the JSON this adapter reads."""


class SlackChannel:
    """One Slack conversation, as the bot whose token this is."""

    def __init__(
        self, base_url: str, channel_id: str, token: str, client: httpx.Client | None = None
    ) -> None:
        if not sendable(token):
            raise ChatError(TOKEN_REFUSED)
        self._base = base_url.rstrip("/")
        self._channel_id = channel_id
        self._token = token
        self._client = client or new_client()
        self._me: ChatUser | None = None

    def post(self, text: str, mentions: Sequence[ChatUser]) -> ThreadRef:
        names = " ".join(f"<@{user.id}>" for user in mentions)
        message = f"{names}\n{_escape(text)}" if names else _escape(text)
        return ThreadRef(id=self._post({"channel": self._channel_id, "text": message}))

    def reply(self, thread: ThreadRef, text: str) -> None:
        self._post({"channel": self._channel_id, "text": _escape(text), "thread_ts": thread.id})

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        after = _parse_cursor(cursor)
        me = self._bot()
        params: dict[str, str | int] = {
            "channel": self._channel_id,
            "ts": thread.id,
            "limit": PER_PAGE,
        }
        if cursor is not None:
            params["oldest"] = cursor
        found: dict[str, Reply] = {}
        pages: set[str] = set()
        for _ in range(MAX_PAGES):
            messages, next_cursor = self._call("GET", "conversations.replies", _page, params=params)
            for message in messages:
                later = after is None or Decimal(message["ts"]) > after
                if later and _is_reply(message, thread, me):
                    found[message["ts"]] = _reply(message, me)
            if not next_cursor:
                return sorted(found.values(), key=lambda reply: Decimal(reply.cursor))
            if next_cursor in pages:
                raise ChatError("unexpected response from conversations.replies")
            pages.add(next_cursor)
            params["cursor"] = next_cursor
        raise ChatError(f"conversations.replies has more than {MAX_PAGES} pages")

    def probe(self) -> str:
        me = self._me or self._call("POST", "auth.test", _identity)
        params = {"channel": self._channel_id}
        is_member, is_archived = self._call("GET", "conversations.info", _membership, params=params)
        if is_archived:
            raise self._error(f"conversations.info: {self._channel_id} is archived")
        if not is_member:
            raise self._error(f"conversations.info: the bot is not a member of {self._channel_id}")
        self._me = me
        return me.handle

    def _bot(self) -> ChatUser:
        if self._me is None:
            self._me = self._call("POST", "auth.test", _identity)
        return self._me

    def _post(self, body: dict[str, str]) -> str:
        return self._call("POST", "chat.postMessage", _ts, body=body)

    def _call[T](
        self,
        verb: str,
        method: str,
        parse: Callable[[dict[str, Any]], T],
        *,
        params: Params | None = None,
        body: dict[str, str] | None = None,
    ) -> T:
        url = f"{self._base}/{method}"
        headers = JSON_UTF8 if body is not None else None
        status, answer_headers, content = exchange(
            self._client, verb, url, self._token, method, params=params, json=body, headers=headers
        )
        if status == _TOO_MANY:
            raise ChatError(f"{method}: 429 rate limited, {_retry_after(answer_headers)}")
        if not httpx.codes.is_success(status):
            cut = content.decode("utf-8", "replace")[:ERROR_BODY_LIMIT]
            raise self._error(f"{method}: {status} {cut}".rstrip())
        try:
            answer = _require(json.loads(content), dict)
        except ValueError, _Unexpected:
            raise ChatError(f"unexpected response from {method}") from None
        if answer.get("ok") is not True:
            raise self._error(f"{method}: {_refusal(answer)}")
        try:
            return parse(answer)
        except KeyError, TypeError, ValueError, _Unexpected:
            raise ChatError(f"unexpected response from {method}") from None

    def _error(self, detail: str) -> ChatError:
        return ChatError(redact_token(detail, self._token))


def _escape(text: str) -> str:
    for character, entity in _ESCAPES:
        text = text.replace(character, entity)
    return text


def _parse_cursor(cursor: str | None) -> Decimal | None:
    if cursor is None:
        return None
    if not _TS.fullmatch(cursor):
        raise ChatError(f"malformed cursor {cursor!r}")
    return Decimal(cursor)


def _retry_after(headers: httpx.Headers) -> str:
    value = headers.get("Retry-After", "")
    return f"Retry-After {value} s" if _RETRY_AFTER.fullmatch(value) else "no Retry-After given"


def _refusal(answer: dict[str, Any]) -> str:
    error, needed = answer.get("error"), answer.get("needed")
    if not isinstance(error, str):
        return "refused without an error code"
    return f"{error} (needed: {needed})" if isinstance(needed, str) else error


def _set(value: object) -> bool:
    """Anything but missing, `None` or `""` counts as set: fail closed."""
    return value is not None and value != ""


def _is_reply(message: dict[str, Any], thread: ThreadRef, me: ChatUser) -> bool:
    if message["ts"] == thread.id or message.get("type", "message") != "message":
        return False
    if any(_set(message.get(field)) for field in NOT_A_PERSON):
        return False
    user = message.get("user")
    if not isinstance(user, str) or not user or user == me.id:
        return False
    return isinstance(message.get("text"), str)


def _unescape(text: str) -> str:
    """`&amp;` goes last, so `&amp;lt;` decodes to `&lt;` and not to `<`."""
    for character, entity in reversed(_ESCAPES):
        text = text.replace(entity, character)
    return text


def _reply(message: dict[str, Any], me: ChatUser) -> Reply:
    raw = message["text"]
    return Reply(
        id=message["ts"],
        author_id=message["user"],
        mentions_bot=slack_mentions_bot(raw, me.id),
        text=_unescape(raw),
        body=_unescape(slack_strip_mentions(raw, me.id)),
        cursor=message["ts"],
    )


def _require[T](value: object, kind: type[T]) -> T:
    if not isinstance(value, kind) or isinstance(value, bool):
        raise _Unexpected
    return value


def _timestamp(value: object) -> str:
    ts = _require(value, str)
    if not _TS.fullmatch(ts):
        raise _Unexpected
    return ts


def _identity(answer: dict[str, Any]) -> ChatUser:
    return ChatUser(id=_require(answer["user_id"], str), handle=_require(answer["user"], str))


def _membership(answer: dict[str, Any]) -> tuple[bool, bool]:
    channel = _require(answer["channel"], dict)
    return channel.get("is_member") is True, channel.get("is_archived") is True


def _ts(answer: dict[str, Any]) -> str:
    return _timestamp(answer["ts"])


def _page(answer: dict[str, Any]) -> Page:
    messages = _require(answer["messages"], list)
    for message in messages:
        _timestamp(_require(message, dict)["ts"])
    meta = answer.get("response_metadata")
    meta = {} if meta is None else _require(meta, dict)
    next_cursor = meta.get("next_cursor")
    return messages, "" if next_cursor is None else _require(next_cursor, str)
