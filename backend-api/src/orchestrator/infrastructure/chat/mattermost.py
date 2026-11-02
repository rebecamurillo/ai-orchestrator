"""`MattermostChannel`: the `ChatChannel` port over Mattermost's REST API v4 (AD-25).

The token goes only to the configured host, as `Authorization: Bearer`, and redirects are
never followed, so a 3xx is a `ChatError` and the bearer cannot reach another host. Every
`ChatError` detail is redacted (AD-5), in the token's raw and escaped forms. A token httpx
could not send is refused at construction, and a request that cannot be built is reported by
exception class only, because those messages quote the header. Nothing is retried (hard rule
7) and nothing is logged. A shared client keeps no cookies, so one bot's session cookie can
never ride along with another bot's requests.

A thread is paged explicitly: the server returns a whole thread for `perPage=0` only "for
now" (`server/channels/api4/post.go::getPostThread`), and without `direction` the order is
undefined. Each page is re-sorted by `(create_at, id)`, the store's own order
(`sqlstore/post_store.go::Get`), rather than trusting `order` to be ascending.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from http.cookiejar import CookieJar, DefaultCookiePolicy
from typing import Any

import httpx

from orchestrator.domain.ports.chat import ChatError, ChatUser, Reply, ThreadRef
from orchestrator.infrastructure.chat.mentions import mentions_bot, strip_mentions
from orchestrator.infrastructure.redact import redact

API = "/api/v4"
TIMEOUT_SECONDS = 10.0
#: The server's `PerPageMaximum`.
PER_PAGE = 200
#: How much of an error body that is not an `AppError` a detail carries.
ERROR_BODY_LIMIT = 300
#: Bounds on one thread read, since `has_next` and a body are the server's to choose.
MAX_PAGES = 50
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
#: `props` flags marking a post someone made through an integration, under their own user id.
INTEGRATION_FLAGS = ("from_webhook", "from_bot", "from_plugin")
#: An integration can post under a person's id with another name or face; never a reply.
OVERRIDE_PROPS = ("override_username", "override_icon_url")
_UNSET_FLAGS = ("", "false")
TOKEN_REFUSED = "the token must be non-empty printable ASCII with no whitespace"

Position = tuple[int, str]


class _Unexpected(Exception):
    """An answer that is not the JSON this adapter reads."""


class _TooLarge(Exception):
    """An answer longer than `MAX_RESPONSE_BYTES`."""


def new_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """The client every channel uses unless given one: bounded, no redirects, no cookies."""
    return httpx.Client(
        timeout=TIMEOUT_SECONDS,
        follow_redirects=False,
        cookies=CookieJar(DefaultCookiePolicy(allowed_domains=[])),
        transport=transport,
    )


class MattermostChannel:
    """One Mattermost channel, as the bot whose token this is."""

    def __init__(
        self, base_url: str, channel_id: str, token: str, client: httpx.Client | None = None
    ) -> None:
        if not _sendable(token):
            raise ChatError(TOKEN_REFUSED)
        self._base = base_url.rstrip("/")
        self._channel_id = channel_id
        self._token = token
        self._client = client or new_client()
        self._me: ChatUser | None = None

    def post(self, text: str, mentions: Sequence[ChatUser]) -> ThreadRef:
        names = " ".join(f"@{user.handle}" for user in mentions)
        message = f"{names}\n{text}" if names else text
        return ThreadRef(id=self._create({"channel_id": self._channel_id, "message": message}))

    def reply(self, thread: ThreadRef, text: str) -> None:
        self._create({"channel_id": self._channel_id, "message": text, "root_id": thread.id})

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
            page, has_next = self._read(path, params, _thread_page)
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
        try:
            with self._client.stream(
                method,
                f"{self._base}{path}",
                params=params,
                json=body,
                headers={"Authorization": f"Bearer {self._token}"},
                follow_redirects=False,
            ) as response:
                status, content = response.status_code, _capped(response)
        except httpx.HTTPError as error:
            raise self._error(f"{type(error).__name__}: {error}") from None
        except (httpx.InvalidURL, ValueError, UnicodeError) as error:
            name = type(error).__name__
            raise ChatError(f"{name}: the request to {path} could not be built") from None
        except _TooLarge:
            raise ChatError(f"{path} answered more than {MAX_RESPONSE_BYTES} bytes") from None
        if not httpx.codes.is_success(status):
            raise self._error(f"{status} {_message(content)}".rstrip())
        try:
            return parse(json.loads(content))
        except ValueError, KeyError, TypeError, _Unexpected:
            raise self._error(f"unexpected response from {path}") from None

    def _error(self, detail: str) -> ChatError:
        token = self._token
        for form in {token, repr(token)[1:-1], repr(token.encode())[2:-1]}:
            detail = redact(detail, form)
        return ChatError(detail)


def _sendable(token: str) -> bool:
    return bool(token) and token.isascii() and token.isprintable() and " " not in token


def _capped(response: httpx.Response) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_RESPONSE_BYTES:
            raise _TooLarge
        chunks.append(chunk)
    return b"".join(chunks)


def _message(content: bytes) -> str:
    try:
        body = json.loads(content)
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("message"), str):
        return body["message"]
    return content.decode("utf-8", "replace")[:ERROR_BODY_LIMIT]


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
