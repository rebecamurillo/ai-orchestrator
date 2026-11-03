"""The close pass, the closing-notice pass and the notice sweep (story 4-2, CAP-12, AD-25).

**Close.** Once per fire, before any Project's passes, every `open` thread whose Run has left
its stop (`rules/chat_close.py::stop_ended`) is closed through 4-1's `close_thread`, the one
close write, which also marks the notice `due` when the thread is on its Project's channel
now. A Project whose channel is off or cannot be opened is included. The check is first made
on an unlocked read, so a stop still waiting takes no lock; an ended one is re-checked under
the Run lock, then the thread's, in its own unit of work. No platform is called.

**Closing notice.** Per Project with an opened channel, after the read pass so 4-1's closes
of this fire get theirs: each `due` thread, oldest `closed_at` first, follows 3-3's post
protocol, claim (`sending`, committed) then reply with no unit of work open and no mention,
then record (`posted` or `failed`) only while it is still `sending`. A thread off the opened
channel is failed at the claim and nothing is posted. At most `WATCH_READS_PER_FIRE` are sent
per Project per fire, and the first `ChatError` ends the pass: the rest stay `due`, never
sent, so a later post is not a repost. Nothing is reposted (hard rule 7).

**Sweep.** At the start of each fire, a notice field still `sending` from before this process
started, or older than `POSTING_STALE_MINUTES`, is failed, each field on its own claim time;
and a `due` notice of a Project with no channel row is failed, since it can never be posted.

A notice failure is logged, never stored in `chat_thread.error` (3-3's D3 meaning). No pass
here writes a status or a gate record (AD-8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Final, Literal

import structlog

from orchestrator.application.jobs.chat_ports import ChatPollPorts, error_class
from orchestrator.application.jobs.chat_post import POSTING_STALE_MINUTES
from orchestrator.application.rules.chat_close import (
    WATCH_READS_PER_FIRE,
    close_line,
    ending_record,
    stop_ended,
)
from orchestrator.application.rules.chat_message import ChatPost, run_link
from orchestrator.application.use_cases.chat_reply import ReplyPorts, close_thread
from orchestrator.domain.entities.chat_thread import ChatThread, NoticeState
from orchestrator.domain.entities.project_channel import ProjectChannel
from orchestrator.domain.ports.chat import ChatChannel, ChatError, ThreadRef

log = structlog.get_logger(__name__)

ABANDONED: Final = "chat close notice abandoned"
FAILED: Final = "chat close notice failed"
SWEEP_FAILED: Final = "chat notice sweep failed"

_Sent = Literal["posted", "failed", "rate_limited", "skipped"]
_Field = Literal["close_notice", "mention_notice"]


def ids(thread: ChatThread) -> dict[str, object]:
    return {"run_id": str(thread.run_id), "thread_id": str(thread.id), "park_seq": thread.park_seq}


def on_channel(thread: ChatThread, channel: ProjectChannel) -> bool:
    return (thread.provider, thread.channel_id) == (channel.provider, channel.channel_id)


def stale(ports: ChatPollPorts, claimed_at: datetime | None, now: datetime) -> bool:
    """Whether a claim made at `claimed_at` can no longer be in flight."""
    if claimed_at is None or claimed_at < ports.started_at:
        return True
    return now - claimed_at > timedelta(minutes=POSTING_STALE_MINUTES)


# ── close ──────────────────────────────────────────────────────────────────────────────


def close_threads(ports: ChatPollPorts) -> None:
    """Close every open thread whose stop has ended, each in its own unit of work."""
    try:
        with ports.chat.writers.uow:
            threads = ports.chat.threads.list_by_state("open")
    except Exception as error:
        log.warning("chat close failed", error_class=error_class(error))
        return
    for thread in threads:
        try:
            _close_if_ended(ports, thread)
        except Exception as error:
            log.warning("chat close failed", **ids(thread), error_class=error_class(error))


def _close_if_ended(ports: ChatPollPorts, thread: ChatThread) -> None:
    chat = ports.chat
    with chat.writers.uow:
        seen = chat.writers.runs.get(thread.run_id)
    if seen is None or not stop_ended(seen, thread):
        return
    with chat.writers.uow:
        run = chat.writers.runs.get_for_update(thread.run_id)
        current = chat.threads.get_for_update(thread.id)
        if run is None or current is None or current.state != "open":
            return
        if not stop_ended(run, current):
            return
        closed = close_thread(_reply_ports(ports), current)
        chat.writers.uow.commit()
    log.info("chat thread closed", **ids(thread), close_notice=closed.close_notice)


def _reply_ports(ports: ChatPollPorts) -> ReplyPorts:
    return ReplyPorts(signal=ports.signal, threads=ports.chat.threads, channels=ports.chat.channels)


# ── closing notice ─────────────────────────────────────────────────────────────────────


def post_close_notices(ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel) -> None:
    """Post the closing notices `due` on the channel's Project, oldest `closed_at` first."""
    try:
        with ports.chat.writers.uow:
            due = ports.chat.threads.list_notices_due(channel.project_id)
    except Exception as error:
        log.warning(FAILED, project_id=str(channel.project_id), error_class=error_class(error))
        return
    sent = 0
    for thread in due:
        if sent >= WATCH_READS_PER_FIRE:
            break
        try:
            outcome = _notice_one(ports, channel, chat, thread)
        except Exception as error:
            log.warning(FAILED, **ids(thread), error_class=error_class(error))
            continue
        if outcome == "rate_limited":
            break
        sent += outcome != "skipped"


def _notice_one(
    ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel, thread: ChatThread
) -> _Sent:
    claimed = _claim_notice(ports, channel, chat, thread)
    if claimed is None:
        return "skipped"
    ref, post = claimed
    try:
        chat.reply(ThreadRef(id=ref), post.text, (), post.suffix)
    except ChatError as error:
        record_notice(ports, thread, "close_notice", "failed", error_class(error))
        return "rate_limited"
    except Exception as error:
        record_notice(ports, thread, "close_notice", "failed", error_class(error))
        return "failed"
    record_notice(ports, thread, "close_notice", "posted", None)
    return "posted"


def _claim_notice(
    ports: ChatPollPorts, channel: ProjectChannel, chat: ChatChannel, thread: ChatThread
) -> tuple[str, ChatPost] | None:
    """The thread's root and its notice, claimed as `sending`; `None` when it is not due
    here, after failing it when it never can be."""
    store = ports.chat
    now = ports.clock.now()
    with store.writers.uow:
        run = store.writers.runs.get_for_update(thread.run_id)
        current = store.threads.get_for_update(thread.id)
        if run is None or current is None or current.close_notice != "due":
            return None
        if current.ref is None or not on_channel(current, channel):
            store.threads.update(
                replace(current, close_notice="failed", close_notice_at=now, updated_at=now)
            )
            store.writers.uow.commit()
            log.warning(ABANDONED, **ids(current), close_notice="failed")
            return None
        ending = ending_record(
            store.writers.records.list_for_run(run.id), run.park_seq, current.park_seq
        )
        post = close_line(
            ending,
            current.park_seq,
            run_link(ports.public_base_url, run.id),
            measure=lambda draft: chat.rendered_length(draft.text, (), draft.suffix),
        )
        store.threads.update(
            replace(current, close_notice="sending", close_notice_at=now, updated_at=now)
        )
        store.writers.uow.commit()
    return current.ref, post


def record_notice(
    ports: ChatPollPorts,
    thread: ChatThread,
    field: _Field,
    outcome: NoticeState,
    failure: str | None,
) -> None:
    """Store a notice's outcome while it is still `sending`; otherwise drop it, logged."""
    store = ports.chat
    kind = "close" if field == "close_notice" else "mention"
    with store.writers.uow:
        current = store.threads.get_for_update(thread.id)
        if current is None or getattr(current, field) != "sending":
            log.warning(f"chat {kind} notice outcome dropped", **ids(thread), **{field: outcome})
            return
        store.threads.update(_with_notice(current, field, outcome, ports.clock.now()))
        store.writers.uow.commit()
    if failure is None:
        log.info(f"chat {kind} notice posted", **ids(thread), **{field: outcome})
    else:
        log.warning(
            f"chat {kind} notice failed", **ids(thread), **{field: outcome}, error_class=failure
        )


def _with_notice(
    thread: ChatThread, field: _Field, state: NoticeState, now: datetime
) -> ChatThread:
    if field == "close_notice":
        return replace(thread, close_notice=state, updated_at=now)
    return replace(thread, mention_notice=state, updated_at=now)


# ── sweep ──────────────────────────────────────────────────────────────────────────────


def sweep_notices(ports: ChatPollPorts) -> None:
    """Fail every interrupted `sending` notice, and every `due` one that has no channel."""
    passes: tuple[tuple[NoticeState, Callable[[ChatPollPorts, ChatThread], None]], ...] = (
        ("sending", _fail_interrupted),
        ("due", _fail_stranded),
    )
    for state, settle in passes:
        try:
            with ports.chat.writers.uow:
                listed = ports.chat.threads.list_notices_in(state)
        except Exception as error:
            log.warning(SWEEP_FAILED, state=state, error_class=error_class(error))
            continue
        for thread in listed:
            try:
                settle(ports, thread)
            except Exception as error:
                log.warning(SWEEP_FAILED, **ids(thread), error_class=error_class(error))


def _fail_interrupted(ports: ChatPollPorts, thread: ChatThread) -> None:
    store = ports.chat
    now = ports.clock.now()
    with store.writers.uow:
        current = store.threads.get_for_update(thread.id)
        if current is None:
            return
        claims: tuple[tuple[_Field, NoticeState | None, datetime | None], ...] = (
            ("close_notice", current.close_notice, current.close_notice_at),
            ("mention_notice", current.mention_notice, current.mention_notice_at),
        )
        failed = [
            field
            for field, state, claimed_at in claims
            if state == "sending" and stale(ports, claimed_at, now)
        ]
        if not failed:
            return
        settled = current
        for field in failed:
            settled = _with_notice(settled, field, "failed", now)
        store.threads.update(settled)
        store.writers.uow.commit()
    for field in failed:
        log.warning("chat notice interrupted", **ids(current), notice=field, state="failed")


def _fail_stranded(ports: ChatPollPorts, thread: ChatThread) -> None:
    store = ports.chat
    now = ports.clock.now()
    with store.writers.uow:
        current = store.threads.get_for_update(thread.id)
        if current is None or current.close_notice != "due":
            return
        run = store.writers.runs.get(current.run_id)
        if run is not None and store.channels.get_current(run.project_id) is not None:
            return
        store.threads.update(
            replace(current, close_notice="failed", close_notice_at=now, updated_at=now)
        )
        store.writers.uow.commit()
    log.warning(ABANDONED, **ids(current), close_notice="failed")
