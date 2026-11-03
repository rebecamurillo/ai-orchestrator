"""Whether a thread reply may answer its stop (story 4-1, CAP-12, AD-24, AD-25). Pure.

**The gate** is checked once per batch: the thread is `open`, its `cursor` is still the one
the batch was read at, and the Project's channel, read now, is the thread's. Otherwise the
whole batch is `superseded` (another poller, or the Run page, moved the thread) or
`channel_changed` (the Project moved to another platform or channel, or dropped it).

**The checks** run per reply, in this order, and the first failure is the outcome:
`not_allowed`, `no_mention`, `stale`, `locked`, `not_answerable`, `bad_text`. `locked` is read
off the Run under its lock, before `validate`, so a session opened after the read still holds
the stop. Only a `blocked` stop takes a reply: at a `checkpoint`, `answer` means *Reject with
a reason* (AD-25, 4-1 amendment), and a thread posted at `budget` keeps its copy when a raise
turns the stop `blocked`, so the thread's own `park_kind` must be `blocked` too.

**Normalising** a body: CRLF and lone CR become LF, then NFC; every `Cc` character but `\\n`
and `\\t` is dropped, as are the bidi controls; the ends are trimmed. An oversized body is
refused, never truncated. Only `text` comes from the reply; the rest of the payload is the
thread's and the allowed list's.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from typing import Any, Final, Literal

from orchestrator.application.rules.signals import validate
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.entities.run import Run
from orchestrator.domain.entities.step_run import StepRun
from orchestrator.domain.errors import DomainError
from orchestrator.domain.ports.chat import ChatUser, Reply
from orchestrator.domain.values import Signal

MAX_ANSWER_CHARS: Final = 8000

#: The only stop a thread reply answers.
REPLY_STOP: Final = "blocked"
#: The signal a passing reply becomes.
ANSWER: Final = "answer"

Outcome = Literal[
    "answered",
    "not_allowed",
    "no_mention",
    "stale",
    "locked",
    "not_answerable",
    "bad_text",
    "superseded",
    "channel_changed",
    "refused",
]

_KEPT_CONTROLS: Final = frozenset({"\n", "\t"})
_BIDI: Final = frozenset(chr(code) for code in (*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


def normalise(body: str) -> str:
    """`body` as an answer's text: LF line ends, NFC, no controls or bidi marks, trimmed."""
    text = unicodedata.normalize("NFC", body.replace("\r\n", "\n").replace("\r", "\n"))
    return "".join(character for character in text if _kept(character)).strip()


def gate(
    thread: ChatThread | None, read_cursor: str | None, channel: ProjectChannel | None
) -> Outcome | None:
    """Why the whole batch is moot, or `None` when its replies are checked."""
    if thread is None or thread.state != "open" or thread.cursor != read_cursor:
        return "superseded"
    if (
        channel is None
        or channel.provider != thread.provider
        or channel.channel_id != thread.channel_id
    ):
        return "channel_changed"
    return None


def check(  # noqa: PLR0911, PLR0913, PLR0917 — the six checks in order, one return each
    channel: ProjectChannel,
    thread: ChatThread,
    reply: Reply,
    run: Run,
    park_row: StepRun | None,
    rows: Sequence[StepRun],
) -> Outcome | None:
    """The first check this reply fails, or `None` when it answers the stop."""
    if _author(channel, reply.author_id) is None:
        return "not_allowed"
    if not reply.mentions_bot:
        return "no_mention"
    if run.status != "needs_you" or run.park_seq != thread.park_seq:
        return "stale"
    if run.senior_session or run.terminal_session:
        return "locked"
    if not _answerable(thread, run, park_row, rows):
        return "not_answerable"
    if not _good_text(normalise(reply.body)):
        return "bad_text"
    return None


def answer_payload(channel: ProjectChannel, thread: ChatThread, reply: Reply) -> dict[str, Any]:
    """The `answer` payload of a reply that passed `check`, so its author is allowed."""
    handle = next(user.handle for user in channel.allowed_users if user.id == reply.author_id)
    return {
        "text": normalise(reply.body),
        "platform": thread.provider,
        "author_id": reply.author_id,
        "author": handle,
    }


def _kept(character: str) -> bool:
    if character in _KEPT_CONTROLS:
        return True
    return unicodedata.category(character) != "Cc" and character not in _BIDI


def _author(channel: ProjectChannel, author_id: str) -> ChatUser | None:
    return next((user for user in channel.allowed_users if user.id == author_id), None)


def _answerable(
    thread: ChatThread, run: Run, park_row: StepRun | None, rows: Sequence[StepRun]
) -> bool:
    if thread.park_kind != REPLY_STOP or run.park_kind != REPLY_STOP:
        return False
    try:
        validate(run, park_row, Signal(kind=ANSWER, stop=thread.park_seq), rows)
    except DomainError:
        return False
    return True


def _good_text(text: str) -> bool:
    if not text or len(text) > MAX_ANSWER_CHARS:
        return False
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True
