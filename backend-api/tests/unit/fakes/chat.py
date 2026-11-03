"""In-memory `ChatChannel` and `ChatChannelFactory` — the one fake for the chat port (AD-18).

Reuse them; do not write another. Replies are scripted per thread and read back the way the
port promises: oldest first, after the given cursor. A cursor the fake never issued is refused
with `ChatError`, as an adapter refuses a malformed one. `follows` orders cursors by when they
were scripted. `read_errors` makes every read of one thread fail (a deleted root, story 4-3),
and `misordered` hands a thread's replies back newest first, as a broken adapter would.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from orchestrator.domain.ports.chat import ChatError, ChatProvider, ChatUser, Reply, ThreadRef

#: What `probe()` answers until a test scripts another handle.
BOT_HANDLE = "bot"
#: How the fake names a mention when it measures a message.
FAKE_MENTION = "@{handle}"


class FakeChatChannel:
    """Records what was posted, answers scripted replies, and fails once on request."""

    def __init__(self, *, probe_handle: str = BOT_HANDLE) -> None:
        self.probe_handle = probe_handle
        self.posts: list[tuple[str, tuple[ChatUser, ...]]] = []
        self.replies: list[tuple[ThreadRef, str]] = []
        self.reply_mentions: list[tuple[ChatUser, ...]] = []
        self.suffixes: list[str] = []
        self.on_send: Callable[[], None] | None = None
        self.reads: list[tuple[ThreadRef, str | None]] = []
        self.probes = 0
        self.read_errors: dict[str, Exception] = {}
        self.misordered: set[str] = set()
        self._threads: dict[str, list[Reply]] = {}
        self._positions: dict[str, int] = {}
        self._error: ChatError | None = None

    def fail_next(self, error: ChatError) -> None:
        """The next call, whichever it is, raises `error` and records nothing."""
        self._error = error

    def script_replies(self, thread: ThreadRef, *replies: Reply) -> None:
        """Append `replies` to the thread, after any scripted before, as new posts arrive."""
        self._threads.setdefault(thread.id, []).extend(replies)
        for reply in replies:
            self._positions.setdefault(reply.cursor, len(self._positions))

    def post(self, text: str, mentions: Sequence[ChatUser], trusted_suffix: str = "") -> ThreadRef:
        self._sending()
        self._raise_scripted()
        self.posts.append((text + trusted_suffix, tuple(mentions)))
        self.suffixes.append(trusted_suffix)
        thread = ThreadRef(id=f"thread-{len(self.posts)}")
        self._threads.setdefault(thread.id, [])
        return thread

    def reply(
        self,
        thread: ThreadRef,
        text: str,
        mentions: Sequence[ChatUser] = (),
        trusted_suffix: str = "",
    ) -> None:
        self._sending()
        self._raise_scripted()
        self.replies.append((thread, text + trusted_suffix))
        self.reply_mentions.append(tuple(mentions))
        self.suffixes.append(trusted_suffix)

    def rendered_length(
        self, text: str, mentions: Sequence[ChatUser] = (), trusted_suffix: str = ""
    ) -> int:
        names = " ".join(FAKE_MENTION.format(handle=user.handle) for user in mentions)
        return len(f"{names}\n" if names else "") + len(text) + len(trusted_suffix)

    def replies_since(self, thread: ThreadRef, cursor: str | None) -> list[Reply]:
        self._raise_scripted()
        self.reads.append((thread, cursor))
        failure = self.read_errors.get(thread.id)
        if failure is not None:
            raise failure
        replies = self._after(self._threads.get(thread.id, []), cursor)
        return replies[::-1] if thread.id in self.misordered else replies

    def follows(self, cursor: str, after: str | None) -> bool:
        position = self._position(cursor)
        return after is None or position > self._position(after)

    def probe(self) -> str:
        self._raise_scripted()
        self.probes += 1
        return self.probe_handle

    def _after(self, scripted: list[Reply], cursor: str | None) -> list[Reply]:
        if cursor is None:
            return list(scripted)
        cursors = [reply.cursor for reply in scripted]
        if cursor not in cursors:
            raise ChatError(f"unknown cursor {cursor!r}")
        return scripted[cursors.index(cursor) + 1 :]

    def _position(self, cursor: str) -> int:
        if cursor not in self._positions:
            raise ChatError(f"unknown cursor {cursor!r}")
        return self._positions[cursor]

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
