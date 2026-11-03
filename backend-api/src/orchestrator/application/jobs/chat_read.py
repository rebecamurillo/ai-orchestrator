"""The read pass (story 4-3, CAP-12, AD-25): every open thread on the Project's current
channel read once per fire, oldest first, and its new replies handed to 4-1's
`apply_reply_batch`, which decides everything again under the Run and thread locks.

The read happens outside any unit of work. A batch the adapter hands back out of order is
refused here as a failed read rather than reordered, so the cursor never moves backwards.

**Each thread is isolated.** A failure is stored as the thread's `error`, under the Run lock
and then the thread's, only while the thread is `open` and only when the value changes, and
`chat read failed` is logged only when it was written: a revoked token gives one line per
thread, not one per fire. A later successful read clears it. Nothing is retried in a fire
(hard rule 7):
- `ChatThreadGone` (the root was deleted) closes the thread with the detail, since every
  later read would fail the same way.
- `ChatRateLimited` stops the pass for this Project; the threads after it wait for the next
  fire. Its `stable` text is stored, without the wait the platform named, so a new wait is
  no new write.
- Anything that is not a `ChatError` is stored and logged as `internal: {class}`, never with
  its message: an SQL error's message carries its bound parameters, here reply text. An
  exception from `apply_reply_batch` writes nothing (4-1), so without this record the same
  reply would fail on every fire unseen. One raised after the batch committed (the engine
  call) finds the thread closed and cannot be stored, so it is logged anyway.

Each checked reply is one line with its outcome, never its text, and never the id of a
refused author. `read_replies` returns `True` when a read failed in this fire, which 4-2's
watch pass reads as "this Project's replies are unknown".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, Literal

import structlog

from orchestrator.application.jobs.chat_notice import INTERNAL
from orchestrator.application.jobs.chat_ports import ChatPollPorts, error_class, redacted
from orchestrator.application.use_cases.chat_reply import (
    ReplyPorts,
    apply_reply_batch,
    close_thread,
)
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import (
    ChatChannel,
    ChatError,
    ChatRateLimited,
    ChatThreadGone,
    Reply,
    ThreadRef,
)

log = structlog.get_logger(__name__)

OUT_OF_ORDER: Final = "the replies came back out of order"
READ_FAILED: Final = "chat read failed"
CHECKED: Final = "chat reply checked"

__all__ = ["INTERNAL", "OUT_OF_ORDER", "read_replies"]

_Read = Literal["ok", "failed", "rate_limited"]
#: What an error write came to: stored, already the stored value, or the thread could not
#: take it (gone, or no longer open).
_Stored = Literal["written", "same", "moot"]


def read_replies(
    ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel, token: str
) -> bool:
    """Read every open thread of the channel's Project once; `True` when a read failed."""
    with ports.chat.writers.uow:
        threads = ports.chat.threads.list_open_for_project(channel.project_id)
    replies = ReplyPorts(
        signal=ports.signal, threads=ports.chat.threads, channels=ports.chat.channels
    )
    failed = False
    for thread in threads:
        if thread.ref is None or not _on_channel(thread, channel):
            continue
        read = _read_one(ports, replies, chat, token, thread, thread.ref)
        failed = failed or read != "ok"
        if read == "rate_limited":
            break
    return failed


def _read_one(  # noqa: PLR0913, PLR0917 — one thread's read, and what it is read through
    ports: ChatPollPorts,
    reply_ports: ReplyPorts,
    chat: ChatChannel,
    token: str,
    thread: ChatThread,
    ref: str,
) -> _Read:
    try:
        replies = chat.replies_since(ThreadRef(id=ref), thread.cursor)
        _in_order(chat, thread.cursor, replies)
    except ChatThreadGone as error:
        detail = redacted(error.detail, token)
        _write(thread, detail, lambda: _close_gone(ports, reply_ports, thread, detail))
        return "failed"
    except ChatRateLimited as error:
        _keep(ports, thread, redacted(error.stable, token))
        return "rate_limited"
    except ChatError as error:
        _keep(ports, thread, redacted(error.detail, token))
        return "failed"
    except Exception as error:
        _keep(ports, thread, INTERNAL.format(name=error_class(error)))
        return "failed"
    _apply(ports, reply_ports, thread, replies)
    return "ok"


def _in_order(chat: ChatChannel, cursor: str | None, replies: Sequence[Reply]) -> None:
    after = cursor
    for reply in replies:
        if not chat.follows(reply.cursor, after):
            raise ChatError(OUT_OF_ORDER)
        after = reply.cursor


def _apply(
    ports: ChatPollPorts, reply_ports: ReplyPorts, thread: ChatThread, replies: Sequence[Reply]
) -> None:
    answered = False
    if replies:
        try:
            results = apply_reply_batch(reply_ports, thread, replies)
        except Exception as error:
            _keep(ports, thread, INTERNAL.format(name=error_class(error)), unstored=True)
            return
        for reply_id, outcome in results:
            log.info(
                CHECKED,
                run_id=str(thread.run_id),
                park_seq=thread.park_seq,
                thread_id=str(thread.id),
                reply_id=reply_id,
                outcome=outcome,
            )
            answered = answered or outcome == "answered"
    if thread.error is not None:
        _write(thread, None, lambda: _set_error(ports, thread, None, closed_ok=answered))


def _keep(ports: ChatPollPorts, thread: ChatThread, detail: str, *, unstored: bool = False) -> None:
    _write(thread, detail, lambda: _set_error(ports, thread, detail), unstored=unstored)


def _write(
    thread: ChatThread,
    detail: str | None,
    write: Callable[[], _Stored],
    *,
    unstored: bool = False,
) -> None:
    """Run one error write. Log `detail` when it was written, and also, with `unstored`,
    when the thread could not take it (closed by the very batch that raised); log the
    write's own failure by class. A value already stored was logged when it was."""
    try:
        stored = write()
    except Exception as error:
        _failed(thread, INTERNAL.format(name=error_class(error)))
        return
    if detail is not None and (stored == "written" or (unstored and stored == "moot")):
        _failed(thread, detail)


def _set_error(
    ports: ChatPollPorts, thread: ChatThread, value: str | None, *, closed_ok: bool = False
) -> _Stored:
    """Store `value` as the thread's `error` if it is still `open` (or `closed` by this
    fire's own answer, with `closed_ok`) and the value changes."""
    chat = ports.chat
    with chat.writers.uow:
        run = chat.writers.runs.get_for_update(thread.run_id)
        current = chat.threads.get_for_update(thread.id)
        if run is None or current is None:
            return "moot"
        if current.state != "open" and not (closed_ok and current.state == "closed"):
            return "moot"
        if current.error == value:
            return "same"
        chat.threads.update(replace(current, error=value, updated_at=ports.clock.now()))
        chat.writers.uow.commit()
    return "written"


def _close_gone(
    ports: ChatPollPorts, reply_ports: ReplyPorts, thread: ChatThread, detail: str
) -> _Stored:
    """Close a thread whose root is gone through 4-1's `close_thread`, with `detail` as its
    `error` and its cursor kept."""
    chat = ports.chat
    with chat.writers.uow:
        run = chat.writers.runs.get_for_update(thread.run_id)
        current = chat.threads.get_for_update(thread.id)
        if run is None or current is None or current.state != "open":
            return "moot"
        close_thread(reply_ports, current, error=detail)
        chat.writers.uow.commit()
    return "written"


def _failed(thread: ChatThread, detail: str) -> None:
    log.warning(
        READ_FAILED,
        run_id=str(thread.run_id),
        thread_id=str(thread.id),
        park_seq=thread.park_seq,
        error=detail,
    )


def _on_channel(thread: ChatThread, channel: ProjectChannel) -> bool:
    return thread.provider == channel.provider and thread.channel_id == channel.channel_id
