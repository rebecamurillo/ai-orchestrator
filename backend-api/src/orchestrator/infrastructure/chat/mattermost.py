"""`MattermostChannel`: the `ChatChannel` port over Mattermost's REST API v4 (AD-25).

The transport rules (bearer only to the configured host, no redirects, no cookies, capped
answers, no retry, no logging) are `http.py`'s, shared with Slack, so a 3xx is a `ChatError`.
Every `ChatError` detail is redacted (AD-5), in the token's raw and escaped forms, and a token
httpx could not send is refused at construction.

A thread is paged explicitly: the server returns a whole thread for `perPage=0` only "for
now" (`server/channels/api4/post.go::getPostThread`), and without `direction` the order is
undefined. Each page is re-sorted by `(create_at, id)`, the store's own order
(`sqlstore/post_store.go::Get`), rather than trusting `order` to be ascending.

Outgoing text is neutralised (story 3-3, D1, as the review of the build tightened it):
`props.disable_group_highlight` does not suppress notifications, so `@channel` in an agent's
question would ping everyone. Every `@` gets U+2060 after it, and `\\`, `[`, `]` and `&` are
backslash-escaped, so no link renders under another text and no entity decodes to an `@`.
Only the adapter's own prefix names people, and only the trusted suffix (the system's own
Run link) is sent as written.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from typing import Any

import httpx

from orchestrator.domain.ports.chat import (
    ChatError,
    ChatRateLimited,
    ChatThreadGone,
    ChatUser,
    Reply,
    ThreadRef,
)
from orchestrator.infrastructure.chat.http import (
    ERROR_BODY_LIMIT,
    MAX_RESPONSE_BYTES,
    TIMEOUT_SECONDS,
    TOKEN_REFUSED,
    excerpt,
    exchange,
    new_client,
    redact_token,
    sendable,
)
from orchestrator.infrastructure.chat.mentions import mentions_bot, strip_mentions

API = "/api/v4"
#: The server's `PerPageMaximum`.
PER_PAGE = 200
#: A handle rendered as `@handle` must be a username, or it could carry `@channel` or a newline.
_USERNAME = re.compile(r"[a-z0-9._-]+")
HANDLE_REFUSED = "a mention's handle is not a Mattermost username"
#: Usernames the server reads as a group mention, never as a person.
GROUP_HANDLES = frozenset({"channel", "here", "all"})
GROUP_REFUSED = "a mention's handle names a group: channel, here or all"
WORD_JOINER = "\u2060"
#: Backslash-escaped in outgoing text, the backslash itself first (story 3-3 review).
_ESCAPED = ("\\", "[", "]", "&")
#: Bounds on one thread read, since `has_next` and a body are the server's to choose.
MAX_PAGES = 50
#: `props` flags marking a post someone made through an integration, under their own user id.
INTEGRATION_FLAGS = ("from_webhook", "from_bot", "from_plugin")
#: An integration can post under a person's id with another name or face; never a reply.
OVERRIDE_PROPS = ("override_username", "override_icon_url")
_UNSET_FLAGS = ("", "false")
_NOT_FOUND = 404
_TOO_MANY = 429

__all__ = [
    "ERROR_BODY_LIMIT",
    "MAX_PAGES",
    "MAX_RESPONSE_BYTES",
    "PER_PAGE",
    "TIMEOUT_SECONDS",
    "TOKEN_REFUSED",
    "MattermostChannel",
    "new_client",
]

Position = tuple[int, str]


class _Unexpected(Exception):
    """An answer that is not the JSON this adapter reads."""


class _NotFound(ChatError):
    """A 404: on the thread read, the root is gone (`ChatThreadGone`); elsewhere a plain
    refusal."""


class MattermostChannel:
    """One Mattermost channel, as the bot whose token this is."""

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

    def post(self, text: str, mentions: Sequence[ChatUser], trusted_suffix: str = "") -> ThreadRef:
        message = _message(text, mentions, trusted_suffix)
        return ThreadRef(id=self._create({"channel_id": self._channel_id, "message": message}))

    def reply(
        self,
        thread: ThreadRef,
        text: str,
        mentions: Sequence[ChatUser] = (),
        trusted_suffix: str = "",
    ) -> None:
        message = _message(text, mentions, trusted_suffix)
        self._create({"channel_id": self._channel_id, "message": message, "root_id": thread.id})

    def rendered_length(
        self, text: str, mentions: Sequence[ChatUser] = (), trusted_suffix: str = ""
    ) -> int:
        return len(_message(text, mentions, trusted_suffix))

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        after = _parse_cursor(cursor)
        me = self._bot()
        path = f"{API}/posts/{thread.id}/thread"
        found: dict[str, tuple[Position, Reply]] = {}
        position = after
        for _ in range(MAX_PAGES):
            params: dict[str, str | int] = {"perPage": PER_PAGE, "direction": "down"}
            if position is not None:
                params["fromCreateAt"], params["fromPost"] = position
            try:
                page, has_next = self._read(path, params, _thread_page)
            except _NotFound as error:
                raise ChatThreadGone(error.detail) from None
            for key, post in page:
                if (after is None or key > after) and _is_reply(post, thread, me):
                    found[post["id"]] = (key, _reply(post, key, me.handle))
            if not has_next or not page:
                return [reply for _, reply in sorted(found.values(), key=lambda item: item[0])]
            last = page[-1][0]
            if position is not None and last <= position:
                raise self._error(f"unexpected response from {path}")
            position = last
        raise self._error(f"{path} has more than {MAX_PAGES} pages")

    def follows(self, cursor: str, after: str | None) -> bool:
        position, since = _parse_cursor(cursor), _parse_cursor(after)
        return since is None or (position is not None and position > since)

    def probe(self) -> str:
        me = self._me or self._read(f"{API}/users/me", None, _user)
        self._read(f"{API}/channels/{self._channel_id}/members/{me.id}", None, _anything)
        self._me = me
        return me.handle

    def _bot(self) -> ChatUser:
        if self._me is None:
            self._me = self._read(f"{API}/users/me", None, _user)
        return self._me

    def _create(self, body: dict[str, str]) -> str:
        return self._send("POST", f"{API}/posts", None, body, _post_id)

    def _read[T](
        self, path: str, params: dict[str, str | int] | None, parse: Callable[[Any], T]
    ) -> T:
        return self._send("GET", path, params, None, parse)

    def _send[T](
        self,
        method: str,
        path: str,
        params: dict[str, str | int] | None,
        body: dict[str, str] | None,
        parse: Callable[[Any], T],
    ) -> T:
        url = f"{self._base}{path}"
        status, _, content = exchange(
            self._client, method, url, self._token, path, params=params, json=body
        )
        if not httpx.codes.is_success(status):
            detail = redact_token(
                f"{status} {_error_message(content, self._token)}".rstrip(), self._token
            )
            if status == _TOO_MANY:
                raise ChatRateLimited(detail)
            if status == _NOT_FOUND:
                raise _NotFound(detail)
            raise ChatError(detail)
        try:
            return parse(json.loads(content))
        except ValueError, KeyError, TypeError, _Unexpected:
            raise self._error(f"unexpected response from {path}") from None

    def _error(self, detail: str) -> ChatError:
        return ChatError(redact_token(detail, self._token))


def neutralise(text: str) -> str:
    """`text` that can open no mention, no link and no entity: `\\` escaped first, so an
    escape in the text cannot cancel one of ours, then `[`, `]` and `&`, and U+2060 after
    every `@`. The adapter's own mention prefix is built apart."""
    for character in _ESCAPED:
        text = text.replace(character, f"\\{character}")
    return text.replace("@", f"@{WORD_JOINER}")


def _message(text: str, mentions: Sequence[ChatUser], trusted_suffix: str = "") -> str:
    if not all(_USERNAME.fullmatch(user.handle) for user in mentions):
        raise ChatError(HANDLE_REFUSED)
    if any(user.handle in GROUP_HANDLES for user in mentions):
        raise ChatError(GROUP_REFUSED)
    names = " ".join(f"@{user.handle}" for user in mentions)
    body = neutralise(text) + trusted_suffix
    return f"{names}\n{body}" if names else body


def _error_message(content: bytes, token: str) -> str:
    try:
        body = json.loads(content)
    except ValueError:
        body = None
    message = body.get("message") if isinstance(body, dict) else None
    if isinstance(message, str):
        return excerpt(message, token)
    return excerpt(content.decode("utf-8", "replace"), token)


def _parse_cursor(cursor: str | None) -> Position | None:
    if cursor is None:
        return None
    create_at, _, post_id = cursor.partition(":")
    if not (create_at.isdigit() and post_id):
        raise ChatError(f"malformed cursor {cursor!r}")
    return int(create_at), post_id


def _is_reply(post: dict[str, Any], thread: ThreadRef, me: ChatUser) -> bool:
    if post["id"] == thread.id or post["user_id"] == me.id or post.get("type"):
        return False
    props = post.get("props") or {}
    if any(name in props for name in OVERRIDE_PROPS):
        return False
    return not any(_flag_set(props.get(flag)) for flag in INTEGRATION_FLAGS)


def _flag_set(value: object) -> bool:
    """Anything but missing, `False`, `""` or `"false"` marks an integration: fail closed."""
    if value is None or value is False:
        return False
    return not (isinstance(value, str) and value.lower() in _UNSET_FLAGS)


def _reply(post: dict[str, Any], key: Position, username: str) -> Reply:
    text = post["message"]
    return Reply(
        id=post["id"],
        author_id=post["user_id"],
        mentions_bot=mentions_bot(text, username),
        text=text,
        body=strip_mentions(text, username),
        cursor=f"{key[0]}:{key[1]}",
    )


def _require[T](value: object, kind: type[T]) -> T:
    if not isinstance(value, kind) or isinstance(value, bool):
        raise _Unexpected
    return value


def _user(body: Any) -> ChatUser:
    return ChatUser(id=_require(body["id"], str), handle=_require(body["username"], str))


def _post_id(body: Any) -> str:
    return _require(body["id"], str)


def _anything(body: Any) -> None:
    return None


def _thread_page(body: Any) -> tuple[list[tuple[Position, dict[str, Any]]], bool]:
    posts = _require(body["posts"], dict)
    page = []
    for post_id in _require(body["order"], list):
        post = _require(posts[post_id], dict)
        for field in ("id", "user_id", "message"):
            _require(post[field], str)
        if post.get("props") is not None:
            _require(post["props"], dict)
        page.append(((_require(post["create_at"], int), post["id"]), post))
    page.sort(key=lambda item: item[0])
    return page, body.get("has_next") is True
