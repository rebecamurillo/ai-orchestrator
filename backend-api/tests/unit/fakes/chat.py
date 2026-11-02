"""In-memory `ChatChannel` and `ChatChannelFactory` — the one fake for the chat port (AD-18).

Reuse them; do not write another. Replies are scripted per thread and read back the way the
port promises: oldest first, after the given cursor. A cursor the fake never issued is refused
with `ChatError`, as an adapter refuses a malformed one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from orchestrator.domain.ports.chat import ChatError, ChatProvider, ChatUser, Reply, ThreadRef

#: What `probe()` answers until a test scripts another handle.
BOT_HANDLE = "bot"


class FakeChatChannel:
    """Records what was posted, answers scripted replies, and fails once on request."""

    def __init__(self, *, probe_handle: str = BOT_HANDLE) -> None:
        self.probe_handle = probe_handle
        self.posts: list[tuple[str, tuple[ChatUser, ...]]] = []
        self.replies: list[tuple[ThreadRef, str]] = []
        self.reply_mentions: list[tuple[ChatUser, ...]] = []
        self.on_send: Callable[[], None] | None = None
        self.reads: list[tuple[ThreadRef, str | None]] = []
        self.probes = 0
        self._threads: dict[str, list[Reply]] = {}
        self._error: ChatError | None = None

    def fail_next(self, error: ChatError) -> None:
        """The next call, whichever it is, raises `error` and records nothing."""
        self._error = error

    def script_replies(self, thread: ThreadRef, *replies: Reply) -> None:
        """Append `replies` to the thread, after any scripted before, as new posts arrive."""
        self._threads.setdefault(thread.id, []).extend(replies)

    def post(self, text: str, mentions: Sequence[ChatUser]) -> ThreadRef:
        self._sending()
        self._raise_scripted()
        self.posts.append((text, tuple(mentions)))
        thread = ThreadRef(id=f"thread-{len(self.posts)}")
        self._threads.setdefault(thread.id, [])
        return thread

    def reply(self, thread: ThreadRef, text: str, mentions: Sequence[ChatUser] = ()) -> None:
        self._sending()
        self._raise_scripted()
        self.replies.append((thread, text))
        self.reply_mentions.append(tuple(mentions))

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        self._raise_scripted()
        self.reads.append((thread, cursor))
        scripted = self._threads.get(thread.id, [])
        if cursor is None:
            return list(scripted)
        cursors = [reply.cursor for reply in scripted]
        if cursor not in cursors:
            raise ChatError(f"unknown cursor {cursor!r}")
        return scripted[cursors.index(cursor) + 1 :]

    def probe(self) -> str:
        self._raise_scripted()
        self.probes += 1
        return self.probe_handle

    def _sending(self) -> None:
        if self.on_send is not None:
            self.on_send()

    def _raise_scripted(self) -> None:
        error, self._error = self._error, None
        if error is not None:
            raise error


class FakeChatChannelFactory:
    """Hands out one `FakeChatChannel`, recording each `open`; refuses when told to."""

    def __init__(self, channel: FakeChatChannel | None = None) -> None:
        self.channel = channel or FakeChatChannel()
        self.opened: list[tuple[ChatProvider, str, str, str]] = []
        self.error: ChatError | None = None

    def open(
        self, provider: ChatProvider, base_url: str, channel_id: str, token: str
    ) -> FakeChatChannel:
        if self.error is not None:
            raise self.error
        self.opened.append((provider, base_url, channel_id, token))
        return self.channel
