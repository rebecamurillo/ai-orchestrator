"""The watch pass (story 4-2, CAP-12, AD-25): one notice for a late mention in a closed
thread.

For `WATCH_HOURS` after it closed, a closed thread on the opened channel whose closing notice
was posted and that has no mention notice is read from `mention_cursor` (or 4-1's `cursor`),
outside any unit of work, the `WATCH_READS_PER_FIRE` newest only. Older ones may go unread
until their window ends: the notice is a courtesy, and 4-1 refuses the reply either way.

The first reply from an allowed person that mentions the bot is claimed under the thread
lock, only while `mention_notice` is unset and `mention_cursor` is what the read started
from: `sending`, its claim time, and the cursor at that reply, committed. The notice is then
sent with no mention and recorded as `posted` or `failed`, so a thread gets one, never one
per mention. With no such reply the cursor moves to the last one read, under the same check.
Outsiders never count, as 4-1 refuses them silently.

A `ChatError` on a read fails the thread's watch for good (`mention_notice` `failed`), and
like a `ChatError` on a notice, ends the pass for the Project this fire. Nothing is retried
(hard rule 7), and nothing here writes a status or a gate record (AD-8).
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Final, Literal

import structlog

from orchestrator.application.jobs.chat_close import guarded, ids, record_notice
from orchestrator.application.jobs.chat_ports import ChatPollPorts, error_class
from orchestrator.application.rules.chat_close import (
    WATCH_HOURS,
    WATCH_READS_PER_FIRE,
    closed_mention_line,
)
from orchestrator.application.rules.chat_message import run_link
from orchestrator.domain.entities.chat_thread import ChatThread
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatChannel, ChatError, Reply, ThreadRef

log = structlog.get_logger(__name__)

_Watch = Literal["ok", "stop"]
WATCH_FAILED: Final = "chat watch failed"


def watch_threads(ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel) -> None:
    """Read the channel's watched threads once, newest closed first."""
    since = ports.clock.now() - timedelta(hours=WATCH_HOURS)
    try:
        with ports.chat.writers.uow:
            watched = ports.chat.threads.list_watched(
                channel.project_id,
                channel.provider,
                channel.channel_id,
                closed_since=since,
                limit=WATCH_READS_PER_FIRE,
            )
    except Exception as error:
        log.warning(
            WATCH_FAILED, project_id=str(channel.project_id), error_class=error_class(error)
        )
        return
    allowed = frozenset(user.id for user in channel.allowed_users)
    for thread in watched:
        try:
            if _watch_one(ports, chat, allowed, thread) == "stop":
                break
        except Exception as error:
            log.warning(WATCH_FAILED, **ids(thread), error_class=error_class(error))


def _watch_one(
    ports: ChatPollPorts, chat: ChatChannel, allowed: frozenset[str], thread: ChatThread
) -> _Watch:
    if thread.ref is None:
        return "ok"
    start = thread.mention_cursor or thread.cursor
    try:
        replies = chat.replies_since(ThreadRef(id=thread.ref), start)
    except ChatError as error:
        guarded(lambda: _fail_watch(ports, thread), WATCH_FAILED, thread)
        log.warning("chat watch read failed", **ids(thread), error_class=error_class(error))
        return "stop"
    counted = _first_counted(replies, allowed)
    if counted is None:
        if replies:
            _claim(ports, thread, replies[-1].cursor, notice=False)
        return "ok"
    if not _claim(ports, thread, counted.cursor, notice=True):
        return "ok"
    return _notify(ports, chat, thread, thread.ref)


def _notify(ports: ChatPollPorts, chat: ChatChannel, thread: ChatThread, ref: str) -> _Watch:
    """Send the claimed notice and record how it went."""
    post = closed_mention_line(
        run_link(ports.public_base_url, thread.run_id),
        measure=lambda draft: chat.rendered_length(draft.text, (), draft.suffix),
    )
    try:
        chat.reply(ThreadRef(id=ref), post.text, (), post.suffix)
    except ChatError as error:
        failure = error_class(error)
        guarded(
            lambda: record_notice(ports, thread, "mention_notice", "failed", failure),
            "chat mention notice failed",
            thread,
        )
        return "stop"
    except Exception as error:
        record_notice(ports, thread, "mention_notice", "failed", error_class(error))
        return "ok"
    record_notice(ports, thread, "mention_notice", "posted", None)
    return "ok"


def _first_counted(replies: list[Reply], allowed: frozenset[str]) -> Reply | None:
    return next((r for r in replies if r.author_id in allowed and r.mentions_bot), None)


def _claim(ports: ChatPollPorts, read: ChatThread, cursor: str, *, notice: bool) -> bool:
    """Move the thread's `mention_cursor` to `cursor`, claiming the notice with `notice`,
    while it is as the read found it; whether it was."""
    store = ports.chat
    now = ports.clock.now()
    with store.writers.uow:
        current = store.threads.get_for_update(read.id)
        if current is None or current.mention_notice is not None:
            return False
        if current.mention_cursor != read.mention_cursor:
            return False
        claimed = replace(current, mention_cursor=cursor, updated_at=now)
        if notice:
            claimed = replace(claimed, mention_notice="sending", mention_notice_at=now)
        store.threads.update(claimed)
        store.writers.uow.commit()
    return True


def _fail_watch(ports: ChatPollPorts, read: ChatThread) -> None:
    store = ports.chat
    now = ports.clock.now()
    with store.writers.uow:
        current = store.threads.get_for_update(read.id)
        if current is None or current.mention_notice is not None:
            return
        store.threads.update(
            replace(current, mention_notice="failed", mention_notice_at=now, updated_at=now)
        )
        store.writers.uow.commit()
